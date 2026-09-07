"""Проверка провайдера LLM до начала разработки.

Отвечает на четыре вопроса:
  1. Живой ли ключ и какие модели отвечают.
  2. Работает ли tool calling (без него агента не существует).
  3. Кэшируется ли префикс промпта (влияет на бюджет в 3-5 раз).
  4. Какая задержка на шаг.

Зависимостей нет — только стандартная библиотека.
Запуск:  python scripts/smoke_llm.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Консоль Windows по умолчанию cp1251 и падает на кириллице и рамках.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, OSError):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ── .env ──────────────────────────────────────────────────────────────


def load_env() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


# ── HTTP ──────────────────────────────────────────────────────────────


def post(url: str, payload: dict, headers: dict, timeout: int = 90) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("content-type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:500]}
    except Exception as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


# ── Тестовый инструмент ───────────────────────────────────────────────
# Намеренно похож на реальный: агент обязан уметь выбрать ref со страницы.

TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "click",
        "description": "Click an element from the current page snapshot.",
        "parameters": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Element ref, e.g. e21"},
                "reason": {"type": "string"},
            },
            "required": ["ref"],
        },
    },
}

TOOL_ANTHROPIC = {
    "name": "click",
    "description": "Click an element from the current page snapshot.",
    "input_schema": TOOL_OPENAI["function"]["parameters"],
}

# ~1.2k символов, чтобы кэш имело смысл включать
BIG_SYSTEM = (
    "You are a browser automation agent. You receive a compressed page snapshot "
    "and choose exactly one tool call per step. Never invent refs. "
) * 12

USER = (
    "Snapshot:\n"
    "[e12] textbox 'Search' = ''\n"
    "[e13] button 'Find'\n"
    "[e21] link 'First result'\n\n"
    "Task: open the first result."
)


# ── Любой OpenAI-совместимый провайдер ────────────────────────────────
# z.ai, Gemini, OpenRouter, локальный vLLM — одинаковый код.


def check_openai_compatible(base: str, key: str, model: str) -> dict:
    if not key:
        return {"skip": "ключ не задан"}
    base = base.rstrip("/")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": BIG_SYSTEM},
            {"role": "user", "content": USER},
        ],
        "tools": [TOOL_OPENAI],
        # GLM-*-flash — reasoning-модели: часть бюджета уходит в reasoning_content
        "max_tokens": 1024,
    }
    t0 = time.time()
    status, data = post(f"{base}/chat/completions", payload, {"authorization": f"Bearer {key}"})
    elapsed = time.time() - t0

    if status != 200:
        return {"ok": False, "status": status, "detail": data, "elapsed": elapsed}

    choice = (data.get("choices") or [{}])[0]
    calls = (choice.get("message") or {}).get("tool_calls") or []
    usage = data.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}

    return {
        "ok": True,
        "elapsed": elapsed,
        "tool_call": calls[0]["function"] if calls else None,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": details.get("cached_tokens"),
    }


# ── Anthropic ─────────────────────────────────────────────────────────


def check_anthropic(model: str) -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/")
    if not key:
        return {"skip": "ANTHROPIC_API_KEY не задан"}

    payload = {
        "model": model,
        # GLM-*-flash — reasoning-модели: часть бюджета уходит в reasoning_content
        "max_tokens": 1024,
        "system": [
            {
                "type": "text",
                "text": BIG_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "tools": [TOOL_ANTHROPIC],
        "messages": [{"role": "user", "content": USER}],
    }
    t0 = time.time()
    status, data = post(
        f"{base}/v1/messages",
        payload,
        {"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    elapsed = time.time() - t0

    if status != 200:
        return {"ok": False, "status": status, "detail": data, "elapsed": elapsed}

    blocks = data.get("content") or []
    tool_use = next((b for b in blocks if b.get("type") == "tool_use"), None)
    usage = data.get("usage") or {}

    return {
        "ok": True,
        "elapsed": elapsed,
        "tool_call": {"name": tool_use["name"], "input": tool_use["input"]} if tool_use else None,
        "prompt_tokens": usage.get("input_tokens"),
        "completion_tokens": usage.get("output_tokens"),
        "cache_write": usage.get("cache_creation_input_tokens"),
        "cache_read": usage.get("cache_read_input_tokens"),
    }


# ── Вывод ─────────────────────────────────────────────────────────────


def report(label: str, result: dict) -> bool:
    if "skip" in result:
        print(f"  {label:<34} — пропущено ({result['skip']})")
        return False

    if not result.get("ok"):
        print(f"  {label:<34} ОШИБКА {result.get('status')}")
        detail = result.get("detail", {})
        msg = (detail.get("error") or {}).get("message") if isinstance(detail, dict) else None
        print(f"      {msg or json.dumps(detail, ensure_ascii=False)[:300]}")
        return False

    call = result.get("tool_call")
    ok_tool = bool(call)
    mark = "OK  " if ok_tool else "ВНИМАНИЕ"

    print(f"  {label:<34} {mark} {result['elapsed']:.1f}s")
    if ok_tool:
        args = call.get("arguments") or call.get("input")
        print(f"      tool call: {call.get('name', 'click')} {args}")
    else:
        print("      МОДЕЛЬ НЕ ВЫЗВАЛА ИНСТРУМЕНТ — она непригодна для агента")

    print(f"      токены: in={result.get('prompt_tokens')} out={result.get('completion_tokens')}")
    cached = result.get("cached_tokens")
    if cached is not None:
        print(f"      кэш: cached_tokens={cached}")
    if result.get("cache_write") is not None or result.get("cache_read") is not None:
        print(f"      кэш: write={result.get('cache_write')} read={result.get('cache_read')}")
    return ok_tool


# Порядок = порядок проверки. Модели берутся из env, иначе — дефолт.
OPENAI_COMPATIBLE = (
    (
        "z.ai",
        "ZAI_API_KEY",
        ("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4"),
        # Бесплатные на аккаунте без баланса. Платные (glm-4.6, glm-5.3-flash)
        # отдают 1113 Insufficient balance.
        ("glm-4.7-flash", "glm-4.5-flash", "glm-4.6v-flash"),
    ),
    (
        "Gemini",
        "GEMINI_API_KEY",
        ("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"),
        ("gemini-2.5-flash", "gemini-2.5-flash-lite"),
    ),
)


def main() -> int:
    load_env()
    print("\nПроверка провайдеров LLM\n" + "─" * 60)

    any_ok = False

    for label, key_var, (base_var, base_default), models in OPENAI_COMPATIBLE:
        key = os.environ.get(key_var, "")
        base = os.environ.get(base_var, base_default)
        print(f"\n{label}  ({base})")
        if not key:
            print(f"  пропущено — {key_var} не задан")
            continue
        for model in models:
            any_ok |= report(model, check_openai_compatible(base, key, model))

    print("\nAnthropic")
    for model in ("claude-haiku-4-5-20251001", "claude-sonnet-5"):
        any_ok |= report(model, check_anthropic(model))

    print("\n" + "─" * 60)
    if any_ok:
        print("Есть рабочая модель с tool calling — можно начинать.\n")
        print("Важно: если во втором прогоне cached_tokens / cache_read остаются")
        print("нулевыми, кэширование префикса не работает — бюджет вырастет в 3-5 раз.\n")
        return 0

    print("Ни одна модель не отработала. Проверьте ключи в .env.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""Приёмка эндпоинта, выдающего себя за Anthropic Messages API.

Зачем. Ключ, купленный у реселлера, может вести куда угодно: к настоящему
Anthropic, к пулу чужих аккаунтов или к чужому продукту, из которого ответ
переупакован в форму Anthropic. Снаружи все три выглядят одинаково — модель
отвечает, tool calling работает. Расходятся они в том, что видно только
замером: живёт ли кэш префикса, соблюдается ли `max_tokens`, не подставлен ли
чужой системный промпт и можно ли верить числам в `usage`.

Скрипт задаёт эти вопросы за один запуск. Ключи он не печатает никогда.

    python scripts/check_provider.py
    python scripts/check_provider.py --base-url https://example.com \\
        --key-env CANDIDATE_KEY --model claude-haiku-4-5

Без аргументов берёт ANTHROPIC_BASE_URL и ANTHROPIC_API_KEY из .env.

Стоимость запуска — около 40 тысяч входных токенов: проверка кэша требует
префикса заведомо выше порога и повторяется трижды.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Порог кэшируемого префикса зависит от модели и доходит до 4096 токенов
# (у Haiku 4.5 — ровно столько). Ниже порога метка `cache_control`
# игнорируется молча, и отрицательный результат ничего не доказывал бы.
# Берём заведомо больше.
PREFIX_TARGET_TOKENS = 6000

# Заголовки, выдающие прослойку между нами и Anthropic.
PROXY_HEADER_HINTS = ("x-", "via", "server", "request-id")
ANTHROPIC_OWN_HEADERS = {
    "x-should-retry",
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "x-envoy-upstream-service-time",
    "x-robots-tag",
}


def build_prefix() -> str:
    """Длинный детерминированный текст под проверку кэша.

    Не повторяющаяся строка: одинаковые куски токенизатор укладывает плотнее
    обычного текста, и размер префикса получился бы непредсказуемым.
    """
    lines = []
    for i in range(1, 421):
        lines.append(
            f"Rule {i}. When the operator asks for item number {i}, respond with a "
            f"short confirmation, record the identifier {i * 7919 % 100003}, and "
            f"continue to the next instruction without further commentary."
        )
    return "\n".join(lines)


class Endpoint:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.last_headers: dict[str, str] = {}

    def post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            json.dumps(payload).encode("utf-8"),
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                self.last_headers = {k.lower(): v for k, v in response.headers.items()}
                return json.load(response)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"HTTP {e.code}: {body}") from e

    def message(self, **payload) -> dict:
        return self.post("/v1/messages", {"model": self.model, **payload})


def check_liveness(endpoint: Endpoint) -> tuple[bool, list[str]]:
    """Отвечает ли вообще, и чем себя называет."""
    data = endpoint.message(max_tokens=16, messages=[{"role": "user", "content": "Say OK."}])
    notes = [
        f"модель в ответе : {data.get('model')}",
        f"формат id       : {str(data.get('id'))[:12]}…",
    ]
    proxy = {
        k: v
        for k, v in endpoint.last_headers.items()
        if any(k.startswith(h) for h in PROXY_HEADER_HINTS) and k not in ANTHROPIC_OWN_HEADERS
    }
    if proxy:
        notes.append("посторонние заголовки:")
        notes.extend(f"    {k}: {v}" for k, v in sorted(proxy.items()))
    else:
        notes.append("посторонних заголовков нет")
    return True, notes


def check_injected_prompt(endpoint: Endpoint) -> tuple[bool, list[str]]:
    """Не подставлен ли перед нашим чужой системный промпт.

    Запрос идёт вообще без `system`. Настоящий Claude в таких условиях
    называет себя ассистентом Anthropic. Если он называет себя чем-то другим —
    IDE, средой разработки, продуктом, — этот текст пришёл не от нас.
    """
    data = endpoint.message(
        max_tokens=120,
        messages=[{"role": "user", "content": "In one sentence: who are you?"}],
    )
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    lowered = text.lower()
    suspicious = [
        w
        for w in ("ide", "development environment", "coding assistant for", "i can't discuss")
        if w in lowered
    ]
    ok = not suspicious
    notes = [f"ответ: {' '.join(text.split())[:160]}"]
    if suspicious:
        notes.append(f"подозрительно: {', '.join(suspicious)} — похоже на чужой промпт")
    return ok, notes


def check_max_tokens(endpoint: Endpoint) -> tuple[bool, list[str]]:
    """Соблюдается ли потолок вывода."""
    asked = 16
    data = endpoint.message(
        max_tokens=asked,
        messages=[{"role": "user", "content": "Count slowly from 1 to 200, one per line."}],
    )
    got = data.get("usage", {}).get("output_tokens", -1)
    ok = 0 <= got <= asked
    notes = [f"запрошено {asked}, получено {got}, stop_reason={data.get('stop_reason')}"]
    if not ok:
        notes.append("потолок не соблюдается — бюджет прогона не ограничен")
    return ok, notes


def check_cache(endpoint: Endpoint, prefix: str) -> tuple[bool, list[str]]:
    """Переходит ли создание кэша в чтение при повторе.

    Один запрос ничего не доказывает: ненулевой `cache_creation` бывает и там,
    где записи на самом деле нет. Доказательство — второй такой же запрос,
    в котором те же токены пришли как `cache_read`.
    """
    payload = dict(
        max_tokens=16,
        system=[{"type": "text", "text": prefix, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "Reply with the single word: ready."}],
    )
    rows, notes = [], []
    for attempt in range(1, 4):
        usage = endpoint.message(**payload).get("usage", {})
        created = usage.get("cache_creation_input_tokens", 0)
        read = usage.get("cache_read_input_tokens", 0)
        rows.append((created, read))
        notes.append(f"попытка {attempt}: создано={created:<6} прочитано={read}")

    size = max(created for created, _ in rows)
    if size < 4096:
        notes.append(
            f"префикс всего {size} токенов — ниже порога, проверка недостоверна; "
            f"увеличьте PREFIX_TARGET_TOKENS"
        )
        return False, notes

    # Со второй попытки те же токены должны прийти как прочитанные.
    ok = any(read >= size * 0.8 for _, read in rows[1:])
    notes.append(
        "кэш работает: повтор пришёл из кэша"
        if ok
        else "кэш не работает: создание никогда не переходит в чтение"
    )
    return ok, notes


def check_accounting(endpoint: Endpoint, prefix: str) -> tuple[bool, list[str]]:
    """Совпадает ли `count_tokens` с тем, что потом выставляется в `usage`.

    Заодно проверяется, считает ли `count_tokens` поле `tools`: шлюзы, которые
    оценивают размер сами, обычно про инструменты забывают.
    """
    tool = {
        "name": "noop",
        "description": "Does nothing. Present only to measure how tools are counted.",
        "input_schema": {
            "type": "object",
            "properties": {"value": {"type": "string", "description": "Ignored"}},
            "required": ["value"],
        },
    }
    body = dict(
        system=[{"type": "text", "text": prefix}],
        messages=[{"role": "user", "content": "Reply with the single word: ready."}],
    )
    notes = []
    try:
        bare = endpoint.post("/v1/messages/count_tokens", {"model": endpoint.model, **body})
        withtools = endpoint.post(
            "/v1/messages/count_tokens",
            {"model": endpoint.model, "tools": [tool] * 8, **body},
        )
    except RuntimeError as e:
        return False, [f"count_tokens недоступен: {e}"]

    counted = bare.get("input_tokens", 0)
    counted_tools = withtools.get("input_tokens", 0)
    billed = endpoint.message(max_tokens=16, **body).get("usage", {})
    billed_total = billed.get("input_tokens", 0) + billed.get("cache_creation_input_tokens", 0)

    notes.append(f"count_tokens без инструментов : {counted}")
    notes.append(f"count_tokens с 8 инструментами: {counted_tools} (+{counted_tools - counted})")
    notes.append(f"фактически в usage           : {billed_total}")

    tools_counted = counted_tools > counted
    if not tools_counted:
        notes.append("поле tools не учитывается — оценка занижает реальный префикс")

    ratio = billed_total / counted if counted else 0
    if counted and not 0.9 <= ratio <= 1.1:
        notes.append(f"расхождение с usage в {ratio:.2f}× — числам оценки верить нельзя")

    return tools_counted and (0.9 <= ratio <= 1.1), notes


CHECKS = [
    ("живость и заголовки", check_liveness, False),
    ("свой системный промпт", check_injected_prompt, False),
    ("max_tokens", check_max_tokens, False),
    ("кэш префикса", check_cache, True),
    ("честность учёта", check_accounting, True),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="адрес эндпоинта; по умолчанию из .env")
    parser.add_argument("--key-env", help="имя переменной с ключом; по умолчанию ANTHROPIC_API_KEY")
    parser.add_argument("--model", default="claude-haiku-4-5")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")

    with contextlib.suppress(ImportError):
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env", override=True)

    base_url = args.base_url or os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    api_key = os.getenv(args.key_env or "ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"ключ не найден в {args.key_env or 'ANTHROPIC_API_KEY'}")
        return 2

    endpoint = Endpoint(base_url, api_key, args.model)
    prefix = build_prefix()

    print(f"эндпоинт : {base_url}")
    print(f"модель   : {args.model}")
    print(f"ключ     : задан, {len(api_key)} симв. (не печатается)")
    print()

    verdicts: list[tuple[str, bool | None]] = []
    for title, check, needs_prefix in CHECKS:
        print(f"── {title} " + "─" * max(0, 56 - len(title)))
        try:
            ok, notes = check(endpoint, prefix) if needs_prefix else check(endpoint)
        except Exception as e:  # приёмка не должна падать целиком из-за одной проверки
            print(f"   не проверено: {e}\n")
            verdicts.append((title, None))
            continue
        for note in notes:
            print(f"   {note}")
        print()
        verdicts.append((title, ok))

    print("── итог " + "─" * 56)
    mark = {True: "да", False: "НЕТ", None: "?"}
    for title, ok in verdicts:
        print(f"   {mark[ok]:<4} {title}")

    critical = dict(verdicts).get("кэш префикса")
    print()
    if critical is True:
        print("Кэш живой: эндпоинт годится для длинных агентских прогонов.")
    elif critical is False:
        print("Кэш мёртв: префикс оплачивается на каждом шаге по полной цене.")
        print("Для агента на десятки шагов это удорожает прогон примерно вдвое.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

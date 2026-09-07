"""Клиент для любого провайдера с OpenAI-совместимым протоколом.

Обслуживает z.ai (GLM), Gemini, OpenRouter, локальный vLLM — разница только
в base_url и именах моделей.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .base import (
    AuthError,
    ImageContent,
    LLMError,
    LLMResponse,
    MalformedResponse,
    Message,
    ModelUnavailable,
    RateLimited,
    ToolCall,
    ToolSpec,
    TransientError,
    Usage,
    parse_tool_arguments,
)

# Коды z.ai, которые приходят с HTTP 429, но повтор не поможет.
_PERMANENT_CODES = {
    "1113",  # Insufficient balance or no resource package
    "1211",  # Unknown model
    "1002",  # Invalid API key
}

# Провайдеры описывают отсутствующую модель по-разному и не всегда кодом.
# Без этого мёртвая модель опрашивалась бы на каждом шаге заново.
_MODEL_GONE_MARKERS = (
    "does not exist",
    "unknown model",
    "model not found",
    "invalid model",
    "insufficient balance",
    "no resource package",
)


class OpenAICompatProvider:
    """Реализация LLMProvider поверх /chat/completions."""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        timeout_s: float = 120.0,
    ) -> None:
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=15.0),
            headers={
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ── публичный API ────────────────────────────────────────────────

    async def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1500,
        temperature: float = 0.0,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [_encode_message(m) for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = [_encode_tool(t) for t in tools]
            payload["tool_choice"] = "auto"

        started = time.monotonic()
        try:
            resp = await self._client.post(f"{self._base_url}/chat/completions", json=payload)
        except httpx.TimeoutException as e:
            raise TransientError(f"таймаут запроса к {self.name}: {e}", model=model) from e
        except httpx.HTTPError as e:
            raise TransientError(f"сетевая ошибка {self.name}: {e}", model=model) from e
        latency = time.monotonic() - started

        if resp.status_code != 200:
            raise _map_error(resp, model=model, provider=self.name)

        try:
            data = resp.json()
        except ValueError as e:
            raise MalformedResponse(
                f"{self.name} вернул не-JSON: {resp.text[:200]!r}", model=model
            ) from e

        # Некоторые прокси отдают ошибку с HTTP 200 в теле.
        if isinstance(data, dict) and data.get("error"):
            raise _map_payload_error(data["error"], status=200, model=model, provider=self.name)

        return _decode_response(data, model=model, latency=latency)


# ── Кодирование запроса ───────────────────────────────────────────────


def _encode_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _encode_image(image: ImageContent) -> dict[str, Any]:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{image.media_type};base64,{image.data_b64}"},
    }


def _encode_message(msg: Message) -> dict[str, Any]:
    if msg.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": msg.tool_call_id or "",
            "content": msg.content,
        }

    out: dict[str, Any] = {"role": msg.role}

    if msg.images:
        parts: list[dict[str, Any]] = []
        if msg.content:
            parts.append({"type": "text", "text": msg.content})
        parts.extend(_encode_image(img) for img in msg.images)
        out["content"] = parts
    else:
        out["content"] = msg.content

    if msg.tool_calls:
        out["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    # обратно уходит строкой — так требует протокол
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in msg.tool_calls
        ]
        # ассистент с вызовами инструментов обязан иметь content, пусть и пустой
        out.setdefault("content", "")

    return out


# ── Разбор ответа ─────────────────────────────────────────────────────


def _decode_response(data: dict[str, Any], *, model: str, latency: float) -> LLMResponse:
    choices = data.get("choices") or []
    if not choices:
        raise MalformedResponse(f"ответ без choices: {str(data)[:200]}", model=model)

    choice = choices[0]
    raw_msg = choice.get("message") or {}

    tool_calls: list[ToolCall] = []
    for item in raw_msg.get("tool_calls") or []:
        fn = item.get("function") or {}
        name = fn.get("name") or ""
        if not name:
            continue
        tool_calls.append(
            ToolCall(
                id=item.get("id") or f"call_{len(tool_calls)}",
                name=name,
                arguments=parse_tool_arguments(fn.get("arguments"), tool=name),
            )
        )

    message = Message(
        role="assistant",
        content=raw_msg.get("content") or "",
        tool_calls=tool_calls,
        # GLM и o-модели кладут ход мысли сюда; в историю он не вернётся
        reasoning=raw_msg.get("reasoning_content") or raw_msg.get("reasoning") or None,
    )

    usage_raw = data.get("usage") or {}
    details = usage_raw.get("prompt_tokens_details") or {}
    usage = Usage(
        input_tokens=int(usage_raw.get("prompt_tokens") or 0),
        output_tokens=int(usage_raw.get("completion_tokens") or 0),
        cached_tokens=int(details.get("cached_tokens") or 0),
    )

    return LLMResponse(
        message=message,
        usage=usage,
        model=data.get("model") or model,
        stop_reason=choice.get("finish_reason") or "",
        latency_s=latency,
    )


# ── Отображение ошибок ────────────────────────────────────────────────


def _map_error(resp: httpx.Response, *, model: str, provider: str):
    try:
        body = resp.json()
    except ValueError:
        body = {}
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return _map_payload_error(err, status=resp.status_code, model=model, provider=provider)

    # z.ai иногда кладёт сообщение в msg на верхнем уровне
    msg = ""
    if isinstance(body, dict):
        msg = str(body.get("msg") or body.get("message") or "")
    text = msg or resp.text[:300]
    return _classify(resp.status_code, code="", message=text, model=model, provider=provider)


def _map_payload_error(err: dict[str, Any], *, status: int, model: str, provider: str):
    return _classify(
        status,
        code=str(err.get("code") or ""),
        message=str(err.get("message") or err.get("msg") or ""),
        model=model,
        provider=provider,
    )


def _classify(status: int, *, code: str, message: str, model: str, provider: str) -> LLMError:
    label = f"{provider}/{model}: {message or 'без описания'}"
    lowered = message.lower()

    if code in _PERMANENT_CODES or any(m in lowered for m in _MODEL_GONE_MARKERS):
        # Часть таких ответов приходит с HTTP 429, но повтор не поможет —
        # это не лимит скорости, а выбывшая модель.
        return ModelUnavailable(label, model=model, status=status)

    if status in (401, 403):
        return AuthError(label, model=model, status=status)
    if status == 404:
        return ModelUnavailable(label, model=model, status=status)
    if status == 429:
        return RateLimited(label, model=model, status=status)
    if status >= 500:
        return TransientError(label, model=model, status=status)
    return LLMError(label, model=model, status=status)

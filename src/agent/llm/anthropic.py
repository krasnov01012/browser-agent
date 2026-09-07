"""Нативный клиент Anthropic.

Отдельный модуль, а не base_url в openai_compat, по трём причинам:
system идёт отдельным полем, результаты инструментов кладутся блоками
в сообщение пользователя, а кэширование требует явных меток cache_control.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from .base import (
    AuthError,
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
)

API_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_s: float = 120.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s, connect=15.0),
            headers={
                "x-api-key": api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        tools: list[ToolSpec] | None = None,
        max_tokens: int = 1500,
        temperature: float = 0.0,
    ) -> LLMResponse:
        system_blocks, turns = _split_system(messages)

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": turns,
        }
        if system_blocks:
            payload["system"] = system_blocks
        if tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]
            # Схемы инструментов неизменны между шагами — кэшируем хвост блока.
            payload["tools"][-1]["cache_control"] = {"type": "ephemeral"}

        started = time.monotonic()
        try:
            resp = await self._client.post(f"{self._base_url}/v1/messages", json=payload)
        except httpx.TimeoutException as e:
            raise TransientError(f"таймаут запроса к anthropic: {e}", model=model) from e
        except httpx.HTTPError as e:
            raise TransientError(f"сетевая ошибка anthropic: {e}", model=model) from e
        latency = time.monotonic() - started

        if resp.status_code != 200:
            raise _map_error(resp, model=model)

        try:
            data = resp.json()
        except ValueError as e:
            raise MalformedResponse(
                f"anthropic вернул не-JSON: {resp.text[:200]!r}", model=model
            ) from e

        return _decode(data, model=model, latency=latency)


# ── Кодирование ───────────────────────────────────────────────────────


def _split_system(messages: list[Message]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """System уходит отдельным полем; остальное сворачивается в чередующиеся ходы."""
    system_blocks: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == "system":
            block: dict[str, Any] = {"type": "text", "text": msg.content}
            if msg.cacheable:
                block["cache_control"] = {"type": "ephemeral"}
            system_blocks.append(block)
            continue

        if msg.role == "tool":
            # У Anthropic результат инструмента — блок внутри сообщения пользователя.
            block = {
                "type": "tool_result",
                "tool_use_id": msg.tool_call_id or "",
                "content": msg.content,
            }
            if turns and turns[-1]["role"] == "user":
                turns[-1]["content"].append(block)
            else:
                turns.append({"role": "user", "content": [block]})
            continue

        blocks: list[dict[str, Any]] = []
        if msg.content:
            blocks.append({"type": "text", "text": msg.content})
        for img in msg.images:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.media_type,
                        "data": img.data_b64,
                    },
                }
            )
        for call in msg.tool_calls:
            blocks.append(
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.arguments,
                }
            )
        if not blocks:
            continue

        if turns and turns[-1]["role"] == msg.role:
            turns[-1]["content"].extend(blocks)
        else:
            turns.append({"role": msg.role, "content": blocks})

    return system_blocks, turns


# ── Разбор ────────────────────────────────────────────────────────────


def _decode(data: dict[str, Any], *, model: str, latency: float) -> LLMResponse:
    blocks = data.get("content") or []
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    for block in blocks:
        kind = block.get("type")
        if kind == "text":
            text_parts.append(block.get("text") or "")
        elif kind == "thinking":
            thinking_parts.append(block.get("thinking") or "")
        elif kind == "tool_use":
            tool_calls.append(
                ToolCall(
                    id=block.get("id") or f"call_{len(tool_calls)}",
                    name=block.get("name") or "",
                    arguments=block.get("input") or {},
                )
            )

    usage_raw = data.get("usage") or {}
    usage = Usage(
        input_tokens=int(usage_raw.get("input_tokens") or 0)
        + int(usage_raw.get("cache_read_input_tokens") or 0)
        + int(usage_raw.get("cache_creation_input_tokens") or 0),
        output_tokens=int(usage_raw.get("output_tokens") or 0),
        cached_tokens=int(usage_raw.get("cache_read_input_tokens") or 0),
    )

    return LLMResponse(
        message=Message(
            role="assistant",
            content="".join(text_parts),
            tool_calls=tool_calls,
            reasoning="".join(thinking_parts) or None,
        ),
        usage=usage,
        model=data.get("model") or model,
        stop_reason=data.get("stop_reason") or "",
        latency_s=latency,
    )


def _map_error(resp: httpx.Response, *, model: str) -> LLMError:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    err = body.get("error") if isinstance(body, dict) else None
    message = str((err or {}).get("message") or resp.text[:300])
    label = f"anthropic/{model}: {message}"
    status = resp.status_code

    if status in (401, 403):
        return AuthError(label, model=model, status=status)
    if status == 404:
        return ModelUnavailable(label, model=model, status=status)
    if status == 429:
        retry_after = resp.headers.get("retry-after")
        return RateLimited(
            label,
            model=model,
            status=status,
            retry_after=float(retry_after) if retry_after and retry_after.isdigit() else None,
        )
    if status >= 500 or status == 529:
        return TransientError(label, model=model, status=status)
    return LLMError(label, model=model, status=status)

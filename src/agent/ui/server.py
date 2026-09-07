"""Веб-панель: постановка задачи, ход работы, вопросы агента.

Одна страница и поток событий через SSE. Браузер агент показывает сам —
панель нужна, чтобы видеть его рассуждения и отвечать на вопросы.

Одновременно выполняется одна задача: браузер общий, параллелить нечего.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from ..browser import BrowserController
from ..config import Settings
from ..core.loop import AgentLoop
from ..llm import LLMRouter
from ..tools import build_registry

log = logging.getLogger(__name__)

STATIC = Path(__file__).parent / "static"
#: пауза между keep-alive, чтобы прокси не рвали SSE
HEARTBEAT_S = 20.0
#: сколько последних событий проигрывается заново при переподключении
REPLAY = 300


@dataclass
class Session:
    """Состояние единственного активного прогона."""

    settings: Settings
    controller: BrowserController
    router: LLMRouter
    #: по очереди на каждую открытую вкладку
    listeners: list[asyncio.Queue[dict]] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    task_handle: asyncio.Task | None = None
    pending_question: asyncio.Future[str] | None = None

    @property
    def busy(self) -> bool:
        return self.task_handle is not None and not self.task_handle.done()

    def publish(self, kind: str, data: dict) -> None:
        """Событие уходит всем подписчикам.

        Одной очереди на всех недостаточно: перезагрузка страницы во время
        прогона оставляет второй поток, и события начинают делиться между
        ними через один.
        """
        event = {"kind": kind, **data}
        self.history.append(event)
        del self.history[:-REPLAY]
        for queue in self.listeners:
            queue.put_nowait(event)

    def subscribe(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        # Новая вкладка догоняет то, что уже произошло, — иначе перезагрузка
        # посреди прогона показывает пустой экран.
        for event in self.history:
            queue.put_nowait(event)
        self.listeners.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict]) -> None:
        with contextlib.suppress(ValueError):
            self.listeners.remove(queue)

    async def ask(self, question: str) -> str:
        loop = asyncio.get_running_loop()
        self.pending_question = loop.create_future()
        try:
            return await self.pending_question
        finally:
            self.pending_question = None

    def answer(self, text: str) -> bool:
        future = self.pending_question
        if future is None or future.done():
            return False
        future.set_result(text)
        return True

    async def run(self, task: str) -> None:
        self.router.budget.reset()
        loop = AgentLoop(
            settings=self.settings,
            controller=self.controller,
            router=self.router,
            registry=build_registry(),
            on_event=self.publish,
            ask_user=self.ask,
        )
        try:
            result = await loop.run(task)
            self.publish(
                "done",
                {
                    "success": result.success,
                    "summary": result.summary,
                    "steps": result.steps,
                    "tokens_in": result.usage.input_tokens,
                    "tokens_out": result.usage.output_tokens,
                    "elapsed": round(result.elapsed_s),
                    "tools": result.tool_counts,
                    "errors": result.error_counts,
                },
            )
        except Exception as e:
            log.exception("прогон упал")
            self.publish("fatal", {"text": f"{type(e).__name__}: {e}"})


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Browser Agent")
    state: dict[str, Session] = {}

    @app.on_event("startup")
    async def startup() -> None:
        controller = BrowserController(settings)
        await controller.start()
        state["session"] = Session(
            settings=settings, controller=controller, router=LLMRouter(settings)
        )
        log.info("панель готова на http://%s:%d", settings.ui_host, settings.ui_port)

    @app.on_event("shutdown")
    async def shutdown() -> None:
        session = state.get("session")
        if session is None:
            return
        if session.task_handle and not session.task_handle.done():
            session.task_handle.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.task_handle
        await session.router.aclose()
        await session.controller.close()

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.post("/api/task")
    async def start_task(payload: dict) -> JSONResponse:
        session = state["session"]
        task = str(payload.get("task") or "").strip()
        if not task:
            return JSONResponse({"error": "пустая задача"}, status_code=400)
        if session.busy:
            return JSONResponse({"error": "задача уже выполняется"}, status_code=409)

        # Новая задача — чистый экран у всех, кто подключится позже.
        session.history.clear()
        session.publish("task", {"text": task})
        session.task_handle = asyncio.create_task(session.run(task))
        return JSONResponse({"started": True})

    @app.post("/api/answer")
    async def answer(payload: dict) -> JSONResponse:
        session = state["session"]
        text = str(payload.get("answer") or "").strip()
        if not session.answer(text or "пользователь ничего не ответил"):
            return JSONResponse({"error": "агент сейчас ничего не спрашивает"}, status_code=409)
        return JSONResponse({"ok": True})

    @app.post("/api/stop")
    async def stop() -> JSONResponse:
        session = state["session"]
        if not session.busy or session.task_handle is None:
            return JSONResponse({"error": "нечего останавливать"}, status_code=409)
        session.task_handle.cancel()
        session.publish("fatal", {"text": "остановлено пользователем"})
        return JSONResponse({"ok": True})

    @app.get("/api/events")
    async def events() -> StreamingResponse:
        session = state["session"]
        return StreamingResponse(
            _stream(session),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    return app


async def _stream(session: Session) -> AsyncIterator[str]:
    queue = session.subscribe()
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    finally:
        # Закрытая вкладка не должна копить события до конца процесса.
        session.unsubscribe(queue)


def serve(settings: Settings) -> None:
    import uvicorn

    uvicorn.run(
        create_app(settings),
        host=settings.ui_host,
        port=settings.ui_port,
        log_level="warning",
    )

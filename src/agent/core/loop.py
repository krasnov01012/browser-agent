"""Агентный цикл.

Посмотреть на состояние → выбрать одно действие → сделать → посмотреть снова.
Никакого заранее заданного плана: что делать дальше, решает модель на каждом
шаге (docs/CONSTRAINTS.md §2.1).
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from ..browser import BrowserController, BrowserUnavailable, PageState
from ..config import Settings
from ..llm import LLMError, LLMRouter, ToolCall, Usage
from ..llm.budget import BudgetExceeded
from ..security import SecurityGuard, describe_target
from ..tools import ToolContext, ToolError, ToolRegistry, ToolResult
from .context import Conversation, Scratchpad, Step
from .ledger import Ledger
from .memory import Memory
from .recovery import NO_TOOL_CALL_NOTICE, Recovery, budget_notice, signature

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
#: Редакцию системного промпта можно подменить, не трогая код: сравнивать их
#: имеет смысл только на одном и том же наборе задач и одной модели, поэтому
#: переключатель вынесен в окружение, а не в аргументы запуска (docs/PROMPTS.md).
SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE") or "system.md"
SYSTEM_PROMPT = (PROMPTS_DIR / SYSTEM_PROMPT_FILE).read_text(encoding="utf-8")

#: тип обработчика событий для UI
EventSink = Callable[[str, dict], None]
#: как спросить пользователя; возвращает его ответ
AskUser = Callable[[str], Awaitable[str]]

#: с чего начинается согласие пользователя на необратимое действие
AFFIRMATIVE = ("да", "ага", "давай", "ок", "подтвер", "разреш", "yes", "y", "ok", "+")
#: сколько раз агент может ткнуться в уже отклонённое действие, прежде чем прогон
#: признаётся зашедшим в тупик
DECLINE_REPEAT_LIMIT = 3

#: какие действия попадают в реестр совершённых
#:
#: Только те, которыми что-то подтверждают. Ввод текста и прокрутку туда писать
#: незачем: они обратимы, а реестр нужен ровно для того, чтобы не сделать
#: необратимое лишний раз (core/ledger.py).
LEDGER_TOOLS = ("click", "press_key")


@dataclass
class RunResult:
    success: bool
    summary: str
    steps: int
    usage: Usage
    tool_counts: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)
    elapsed_s: float = 0.0
    run_id: str = ""

    def report(self) -> str:
        tools = ", ".join(f"{k}×{v}" for k, v in sorted(self.tool_counts.items()))
        errors = ", ".join(f"{k}×{v}" for k, v in sorted(self.error_counts.items()))
        lines = [
            self.summary,
            "",
            f"шагов {self.steps}, время {self.elapsed_s:.0f} c",
            f"токенов {self.usage}",
            f"инструменты: {tools or '—'}",
            f"ошибки: {errors or 'нет'}",
        ]
        return "\n".join(lines)


class AgentLoop:
    def __init__(
        self,
        *,
        settings: Settings,
        controller: BrowserController,
        router: LLMRouter,
        registry: ToolRegistry,
        on_event: EventSink | None = None,
        ask_user: AskUser | None = None,
        memory: Memory | None = None,
        guard: SecurityGuard | None = None,
    ) -> None:
        self._settings = settings
        self._controller = controller
        self._router = router
        self._registry = registry
        self._on_event = on_event or (lambda kind, data: None)
        self._ask_user = ask_user
        self._memory = memory or Memory(settings.memory_dir, enabled=settings.persist_memory)
        self._guard = guard or SecurityGuard(router, enabled=settings.confirm_destructive)
        self._log_file: Path | None = None

    # ── публичный вход ───────────────────────────────────────────────

    async def run(self, task: str) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        started = time.monotonic()
        self._open_log(run_id)

        scratchpad = Scratchpad()
        conversation = Conversation(
            task=task, scratchpad=scratchpad, recalled=self._memory.recall()
        )
        recovery = Recovery()
        ledger = Ledger()
        ctx = ToolContext(controller=self._controller, scratchpad=scratchpad, router=self._router)

        self._emit("run_started", {"run_id": run_id, "task": task})

        previous: PageState | None = None
        wait_for_settle = True
        outcome: ToolResult | None = None
        stop_reason = ""
        #: подписи действий, на которые пользователь уже ответил «нет»
        declined: set[str] = set()
        #: подписи элементов оттуда же — ref живёт один шаг, подпись переживает
        #: пересборку страницы, и «Отправить» после отказа остаётся тем же
        #: «Отправить», даже если снапшот выдал ему новый номер
        declined_labels: set[str] = set()
        declined_repeats = 0

        while True:
            try:
                self._router.budget.start_step()
            except BudgetExceeded as e:
                stop_reason = str(e)
                break

            try:
                state = await self._controller.snapshot(wait=wait_for_settle)
            except (BrowserUnavailable, PlaywrightError) as e:
                # Единственное место цикла, где до сих пор можно было упасть
                # наружу: снимок снимается вне try. Браузер закрыли — прогон
                # кончился, но кончиться он должен как прогон, с отчётом и
                # накопленными фактами, а не трейсбеком в середине набора
                # (docs/ADR.md ADR-031).
                stop_reason = f"браузер перестал отвечать: {e}"
                break
            ctx.state = state
            state_text = state.diff(previous)
            previous = state
            state_key = state.fingerprint()

            notice = "\n\n".join(
                part
                for part in (
                    recovery.notice(),
                    budget_notice(self._router.budget.exhaustion, self._router.budget.steps_left),
                    ledger.notice(),
                )
                if part
            )

            step_index = self._router.budget.steps
            self._emit(
                "step",
                {
                    "index": step_index,
                    "url": state.url,
                    "elements": len(state.elements),
                    "state_tokens": state.tokens,
                },
            )

            try:
                response = await self._router.call(
                    "navigator",
                    conversation.build(
                        system_prompt=SYSTEM_PROMPT,
                        state_text=state_text,
                        notice=notice,
                    ),
                    tools=self._registry.specs(),
                )
            except LLMError as e:
                stop_reason = f"модель недоступна: {e}"
                break

            if response.message.reasoning:
                self._emit("thought", {"text": response.message.reasoning})

            calls = response.message.tool_calls
            if not calls:
                self._emit("warning", {"text": "модель не вызвала инструмент"})
                conversation.record(
                    Step(
                        index=step_index,
                        call=None,
                        result=NO_TOOL_CALL_NOTICE,
                        reasoning=response.message.reasoning,
                        error_kind="no_tool_call",
                    )
                )
                self._write_log({"step": step_index, "event": "no_tool_call"})
                wait_for_settle = False
                continue

            call = calls[0]
            self._emit("tool_call", {"name": call.name, "arguments": call.arguments})

            sig = signature(call.name, call.arguments)
            target = describe_target(call.arguments, state)
            repeated = sig in declined or target in declined_labels
            refusal = await self._confirm(call, sig, target, state, declined, declined_labels)
            if refusal is not None:
                conversation.record(
                    Step(
                        index=step_index,
                        call=call,
                        result=refusal,
                        reasoning=response.message.reasoning,
                        error_kind="declined",
                    )
                )
                self._write_log({"step": step_index, "tool": call.name, "event": "declined"})
                recovery.observe(
                    call.name,
                    call.arguments,
                    failed=True,
                    state_key=state_key,
                    changed=False,
                )
                if repeated:
                    declined_repeats += 1
                    if declined_repeats >= DECLINE_REPEAT_LIMIT:
                        stop_reason = (
                            "агент раз за разом возвращался к действию, которое "
                            "пользователь отклонил"
                        )
                        break
                wait_for_settle = False
                continue

            try:
                result = await self._registry.invoke(call.name, call.arguments, ctx)
                error_kind = None
            except ToolError as e:
                result = ToolResult(text=e.for_model(), state_changed=False)
                error_kind = e.kind
                self._emit("tool_error", {"name": call.name, "kind": e.kind})
            except Exception as e:
                # Непредусмотренная ошибка не должна убивать автономный прогон:
                # превращаем её в обычный результат, чтобы агент увидел и
                # попробовал другой путь.
                log.exception("инструмент %s упал", call.name)
                result = ToolResult(
                    text=(
                        f"Инструмент {call.name} завершился неожиданной ошибкой "
                        f"({type(e).__name__}). Попробуйте другой способ."
                    ),
                    state_changed=False,
                )
                error_kind = "crash"
                self._emit("tool_error", {"name": call.name, "kind": "crash"})

            self._emit(
                "tool_result",
                {"name": call.name, "text": result.text[:400], "error": error_kind},
            )
            self._write_log(
                {
                    "step": step_index,
                    "url": state.url,
                    "state_tokens": state.tokens,
                    # Без хода мысли журнал отвечает «что сделал», но не «почему».
                    # Разбор застрявшего прогона начинается именно со второго
                    # вопроса: одинаковые клики по одной кнопке выглядят
                    # упрямством, а на деле модель каждый раз объясняет их
                    # по-новому — и объяснение показывает, чего ей не хватает
                    # в снапшоте.
                    "thought": (response.message.reasoning or "")[:600],
                    "tool": call.name,
                    "arguments": call.arguments,
                    "error": error_kind,
                    "result": result.text[:1000],
                    "usage": {
                        "in": response.usage.input_tokens,
                        "out": response.usage.output_tokens,
                        "cached": response.usage.cached_tokens,
                    },
                    "latency_s": round(response.latency_s, 2),
                }
            )

            recovery.observe(
                call.name,
                call.arguments,
                failed=error_kind is not None,
                kind=error_kind or "",
                state_key=state_key,
                changed=result.state_changed,
            )
            if error_kind is None and call.name in LEDGER_TOOLS:
                ledger.add(target)
            conversation.record(
                Step(
                    index=step_index,
                    call=call,
                    result=result.text,
                    reasoning=response.message.reasoning,
                    image_b64=result.image_b64,
                    error_kind=error_kind,
                )
            )

            if result.question is not None:
                answer = await self._resolve_question(result.question)
                conversation.record_answer(result.question, answer)

            if result.finished:
                outcome = result
                break

            wait_for_settle = result.state_changed

        return self._finalize(
            run_id=run_id,
            started=started,
            conversation=conversation,
            outcome=outcome,
            stop_reason=stop_reason,
        )

    # ── вспомогательное ──────────────────────────────────────────────

    async def _confirm(
        self,
        call: ToolCall,
        sig: str,
        target: str,
        state: PageState | None,
        declined: set[str],
        declined_labels: set[str],
    ) -> str | None:
        """Спрашивает пользователя перед необратимым действием.

        Возвращает None, если действие разрешено, иначе — текст отказа
        для модели. Выключено по умолчанию (docs/CONSTRAINTS.md §4).
        """
        if not self._guard.enabled:
            return None
        if sig in declined or target in declined_labels:
            # Один отказ действует до конца прогона. Иначе агент возвращается
            # к той же кнопке и дёргает пользователя одним и тем же вопросом.
            #
            # Отказ запоминается и по подписи элемента, а не только по аргументам
            # вызова. Номера ref раздаются заново на каждом снапшоте: пользователь
            # отклонял кнопку отправки на e94, агент возвращался к той же кнопке
            # под номером e87 — подпись вызова другая, кэш отказов промахивался,
            # и вопрос задавался снова (docs/ADR.md ADR-039).
            return (
                "Это действие пользователь уже отклонил, и оно отклонено окончательно "
                "— повторно спрашивать его я не буду. Оно не будет выполнено ни сейчас, "
                "ни позже. Либо идите к цели другим путём, либо вызовите finish "
                "с success=false и напишите, что действие не согласовано."
            )
        try:
            tool = self._registry.get(call.name)
        except ToolError:
            # Несуществующий инструмент разберёт invoke — с понятной ошибкой.
            return None

        question = await self._guard.confirmation_for(tool, call.arguments, state)
        if question is None:
            return None

        answer = await self._resolve_question(question)
        if answer.strip().lower().startswith(AFFIRMATIVE):
            return None

        declined.add(sig)
        if call.arguments.get("ref"):
            declined_labels.add(target)
        return (
            f"Пользователь не подтвердил это действие, оно не выполнено. "
            f"Его ответ: «{answer}». Больше к этому действию не возвращайтесь: "
            f"выберите другой путь или завершите задачу."
        )

    async def _resolve_question(self, question: str) -> str:
        self._emit("question", {"text": question})
        if self._ask_user is None:
            return (
                "Спросить пользователя сейчас не у кого — принимайте решение сами "
                "или завершайте задачу с объяснением, чего не хватило."
            )
        answer = await self._ask_user(question)
        self._emit("answer", {"text": answer})
        return answer

    def _finalize(
        self,
        *,
        run_id: str,
        started: float,
        conversation: Conversation,
        outcome: ToolResult | None,
        stop_reason: str,
    ) -> RunResult:
        elapsed = time.monotonic() - started

        # В память уезжает только то, что агент выяснил сам за этот прогон.
        self._memory.remember_all(conversation.scratchpad.facts, conversation.task)
        self._memory.save()

        if outcome is not None:
            success, summary = outcome.success, outcome.text
        else:
            success = False
            # Даже прерванный прогон должен что-то сообщить: сначала накопленные
            # факты, иначе — след последних шагов.
            tail = conversation.scratchpad.render()
            if not tail and conversation.steps:
                recent = "\n".join(s.summary() for s in conversation.steps[-5:])
                tail = f"Последние шаги:\n{recent}"
            summary = f"Задача не доведена до конца: {stop_reason or 'цикл прерван'}.\n" + (
                tail or "Ничего сделать не успел."
            )

        result = RunResult(
            success=success,
            summary=summary,
            steps=self._router.budget.steps,
            usage=self._router.budget.usage,
            tool_counts=conversation.tool_counts(),
            error_counts=conversation.error_counts(),
            elapsed_s=elapsed,
            run_id=run_id,
        )
        self._write_log({"event": "finished", "success": success, "steps": result.steps})
        self._emit("run_finished", {"success": success, "summary": summary})
        return result

    def _emit(self, kind: str, data: dict) -> None:
        try:
            self._on_event(kind, data)
        except Exception:
            log.exception("обработчик события упал")

    def _open_log(self, run_id: str) -> None:
        directory = self._settings.log_dir
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self._log_file = directory / f"{run_id}.jsonl"
        except OSError as e:
            log.warning("не удалось открыть журнал: %s", e)
            self._log_file = None

    def _write_log(self, record: dict) -> None:
        if self._log_file is None:
            return
        try:
            with self._log_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            log.debug("журнал недоступен: %s", e)

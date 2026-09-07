"""Мета-инструменты: вопрос пользователю, память, завершение."""

from __future__ import annotations

from .errors import BadArguments
from .registry import Tool, ToolContext, ToolResult, make_tool, p_bool, p_str


@make_tool(
    "ask_user",
    "Ask the user a question and wait for their answer. This is the only way to "
    "pause. Use it when you genuinely cannot proceed — a login is required, a "
    "mandatory detail is missing, or two options are both plausible and the choice "
    "matters. Do not use it to avoid making a decision you can make yourself.",
    properties={"question": p_str("What you need from the user, in one or two sentences")},
    required=["question"],
)
async def ask_user(ctx: ToolContext, question: str) -> ToolResult:
    text = question.strip()
    if not text:
        raise BadArguments("ask_user", "вопрос пуст")
    return ToolResult(text=f"Вопрос пользователю: {text}", state_changed=False, question=text)


@make_tool(
    "remember",
    "Save a fact you will need later. Saved facts stay in front of you for the whole "
    "task even after older steps are summarised away, so put findings here as you "
    "collect them rather than hoping to recall them.",
    properties={"fact": p_str("One fact, stated plainly and completely")},
    required=["fact"],
)
async def remember(ctx: ToolContext, fact: str) -> ToolResult:
    text = fact.strip()
    if not text:
        raise BadArguments("remember", "факт пуст")
    ctx.scratchpad.add(text)
    return ToolResult(text=f"Запомнено ({len(ctx.scratchpad)} всего): {text}", state_changed=False)


@make_tool(
    "finish",
    "End the task and report to the user. Write the summary for a person who did not "
    "watch you work: what you did, what you found, what you changed. Set success=false "
    "if you could not complete the task, and say what blocked you.",
    properties={
        "summary": p_str("Report for the user"),
        "success": p_bool("Whether the task was completed (default true)"),
    },
    required=["summary"],
)
async def finish(ctx: ToolContext, summary: str, success: bool = True) -> ToolResult:
    text = summary.strip()
    if not text:
        raise BadArguments("finish", "отчёт пуст — напишите, что было сделано")
    return ToolResult(text=text, state_changed=False, finished=True, success=bool(success))


TOOLS: list[Tool] = [ask_user, remember, finish]

# AGENTS.md

Instructions for AI coding agents (Codex, Claude Code, Cursor) working in this repository.
Read this **before** touching any file. Read `docs/ARCHITECTURE.md` before writing code in `src/`.

---

## 1. What this project is

An autonomous AI agent that drives a **real, visible Chrome browser** to complete
multi-step tasks given in natural language ("read my last 10 emails and delete spam",
"find 3 AI-engineer vacancies on hh.ru and apply with a cover letter").

This is a **take-home assignment**. It is graded on architecture and research quality,
not on feature count. Reviewers will read the source. Optimise for a codebase that is
obviously well-reasoned over one that is merely large.

---

## 2. Hard constraints — violating these fails the project

These come from the assignment brief. They are not style preferences.

**[`docs/CONSTRAINTS.md`](docs/CONSTRAINTS.md) is the normative document** — it has the
verbatim requirements, the grey-zone rulings (cookie banners, few-shot examples,
cross-session memory, consolidated tools), the grep checks and the pre-submission
checklist. Read it before making any judgement call about what is allowed. The summary
below is the short form.

### 2.1 No hardcoded selectors

**NEVER** write a CSS/XPath selector that targets application content.

```python
# FORBIDDEN
await page.click("a[data-qa='vacancy-serp__vacancy-title']")
await page.query_selector(".mail-MessageSnippet-Content")
if "hh.ru/search/vacancy" in url:
    ...
```

The agent must derive every target from a page snapshot at runtime. The **only**
selectors allowed anywhere in this repo are structural ones inside the snapshot
collector (`src/agent/browser/js/collect.js`) that enumerate the DOM generically —
e.g. `document.querySelectorAll('*')`, `[role]`, `input, button, a, select, textarea`.
Those describe *HTML*, not *any particular website*.

### 2.2 No scripted action sequences

**NEVER** encode task-specific steps. There is no `delete_spam()` function, no
`apply_to_vacancy()` workflow, no ordered list of steps for any site. The agent decides
the next action at every step from the current page state. If you feel the urge to add
`if task_type == "email"`, stop — that is the failure mode being tested for.

### 2.3 No navigational hints

**NEVER** tell the model where things live. Not in prompts, not in config, not in
comments the model can see:

```
# FORBIDDEN in any prompt
"On hh.ru, vacancies are at /search/vacancy"
"The 'Add to cart' button usually says «Заказать»"
"Yandex Mail's spam folder is in the left sidebar"
```

Prompts describe **capabilities and strategy in general terms** ("scroll to reveal more
items", "if an element is covered, close the overlay first"). They never describe
a specific site.

### 2.4 Never send a whole page to the model

Raw HTML of a real SPA is 300k–3M tokens. Every page must go through the snapshot
layer, which produces a filtered, compressed representation. If you find yourself
writing `page.content()` into a message, you have broken the core requirement.

---

## 3. Stack

| Concern | Choice | Note |
|---|---|---|
| Language | Python 3.12 | type hints everywhere, `from __future__ import annotations` |
| Browser | Playwright (`playwright.async_api`) | connect to running Chrome over CDP |
| LLM | provider-agnostic adapter | Gemini 2.5 Flash now, Claude later — see §6 |
| UI | FastAPI + SSE + one static HTML page | plus a thin terminal REPL |
| Packaging | `pyproject.toml`, `uv` or `pip` | Docker for the agent only |
| Async | everything `async` | no sync Playwright API |

Do not add dependencies without a line in `docs/ADR.md` explaining why.

**Explicitly banned dependencies:** `browser-use`, `stagehand`, `skyvern`,
`nanobrowser`, `lavague`, `agentql`, `helium`, or any library that contains an agent
loop or an LLM-driven `act()` primitive. Those implement the exact thing this assignment
asks us to build. Playwright, readability/trafilatura, and LLM SDKs are fine —
they are infrastructure. The dividing line: **who decides what to click.** If a library
does, it is banned; if our model does, it is fine.

**Tool design principles** (adapted from Anthropic's tool-writing guidance, with the
assignment's constraints applied) live in [`docs/TOOLS.md`](docs/TOOLS.md) under
"Принципы". The one that most often trips people up: consolidating tools is good for
*mechanics* (`scroll` + re-snapshot in one call) and forbidden for *scenarios*
(`apply_to_vacancy` is a scripted action — see CONSTRAINTS §2.1).

---

## 4. Repository layout

```
src/agent/
  config.py          Settings from env (pydantic-settings)
  main.py            Entrypoint: parses args, starts UI, CLI or the MCP server

  llm/
    base.py          LLMProvider protocol, Message/ToolCall/Usage dataclasses
    gemini.py        Gemini via its OpenAI-compatible endpoint
    anthropic.py     Native Anthropic API (prompt caching via cache_control)
    router.py        role -> model mapping, fallback chain, retry on 429
    budget.py        Token accounting and hard caps

  browser/
    controller.py    Playwright lifecycle, CDP attach, tab registry, dialogs
    snapshot.py      AX-tree + DOM hybrid -> PageState; delta computation
    refs.py          ref <-> backendNodeId registry, staleness detection
    stability.py     DOM-settle detector (MutationObserver + in-flight requests)
    extract.py       Readable-content extraction -> Markdown
    marks.py         Set-of-Mark screenshot for the vision fallback
    js/collect.js    Injected DOM walker (the ONLY place with generic selectors)
    js/stability.js  Injected mutation/network observer

  tools/
    registry.py      @tool decorator -> JSON schema generation
    navigation.py    goto, go_back, switch_tab, list_tabs, close_tab
    interaction.py   click, type_text, select_option, press_key, scroll, upload_file
    reading.py       read_page, find_in_page, screenshot
    meta.py          ask_user, remember, update_plan, finish
    errors.py        ToolError taxonomy

  core/
    loop.py          The agent loop
    context.py       Message history, compaction, delta snapshots
    memory.py        Cross-session fact store (JSON)
    recovery.py      Error-recovery pattern (advanced pattern #1)
    subagent.py      Extractor sub-agent (advanced pattern #2)

  security/
    guard.py         Destructive-action gate (advanced pattern #3)

  mcp/
    session.py       Browser lifecycle + snapshot freshness for a loopless caller
    server.py        MCP stdio server: Tool.spec() -> protocol, no hand-written schemas

  ui/
    server.py        FastAPI + SSE event stream
    static/index.html
    cli.py           Terminal REPL

  prompts/
    system.md        Main agent system prompt
    extractor.md     Sub-agent prompt

evals/               Task suite + runner
scripts/             launch_chrome.ps1, smoke_llm.py
```

---

## 5. Coding conventions

- **File size ceiling: 400 lines.** Split before exceeding it. This is a token-budget
  rule as much as a style rule — agents re-read files constantly.
- Type-hint every public function. Dataclasses over dicts for anything crossing a
  module boundary.
- `async` everywhere in `browser/`, `llm/`, `core/`. No `asyncio.run` outside `main.py`.
- Errors that the model must see are `ToolError` subclasses with a `.for_model()`
  method returning a short, actionable string. Never leak a Python traceback into
  a message to the LLM — it wastes tokens and teaches nothing.
- Logging: structured JSONL to `runs/<run_id>.jsonl`, one object per step. Human-readable
  lines go to stderr. **Never print a full snapshot to stdout** — it will end up pasted
  into a chat context and burn a usage window.
- **Comments, docstrings, prompts, docs and UI strings are Russian** — the reviewers
  read Russian and it makes the reasoning easier to follow. Code identifiers, log keys
  and error-type names stay English. `RUF001`–`RUF003` are disabled in `pyproject.toml`
  for this reason; do not "fix" Cyrillic by transliterating it.
- **Windows console is cp1251 and crashes on Cyrillic or box-drawing characters.**
  Every entrypoint script must start with a guarded
  `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`. All file I/O must
  pass `encoding="utf-8"` explicitly — the platform default is not UTF-8 here.

---

## 6. LLM provider rules

The agent must run on **any** provider without code changes outside `llm/`.
Configuration is by env var only:

```
LLM_PROVIDER=zai               # zai | gemini | anthropic
ZAI_BASE_URL=https://api.z.ai/api/paas/v4
MODEL_NAVIGATOR=glm-4.6v-flash
MODEL_EXTRACTOR=glm-4.5-flash
MODEL_VISION=glm-4.6v-flash
MODEL_FALLBACK=glm-4.5-flash
```

Swapping to Claude must be a `.env` edit, nothing more:

```
LLM_PROVIDER=anthropic
MODEL_NAVIGATOR=claude-haiku-4-5-20251001
MODEL_EXTRACTOR=claude-haiku-4-5-20251001
MODEL_VISION=claude-sonnet-5
MODEL_FALLBACK=claude-haiku-4-5-20251001
```

Rules:
- `llm/base.py` defines the contract. Provider modules implement it. **Nothing outside
  `llm/` may import a provider module or an SDK directly.**
- z.ai, Gemini and OpenRouter are all OpenAI-shaped: one client implementation serves
  them, differing only by base URL. Anthropic gets its own module (native message
  format + `cache_control`).
- **GLM free-tier models are reasoning models.** They return `reasoning_content`
  alongside `content` and spend part of `max_tokens` on it. Keep `MAX_OUTPUT_TOKENS`
  at 1500+; parse `reasoning_content` into `Message.reasoning`, show it in the UI,
  and **never** feed it back into the next step's history. See ADR-011.
- **Free tiers return 429 under load** (measured: `glm-4.7-flash` failed on the second
  consecutive run). Retry with exponential backoff, then fall through
  `MODEL -> MODEL_FALLBACK -> other provider`. A 429 must never kill a task in progress.
- Prompt caching is provider-specific: Anthropic needs explicit `cache_control` markers,
  z.ai and Gemini cache implicitly. Both live behind the same `cacheable=True` flag.
  Note `glm-4.6v-flash` does **not** cache — delta snapshots carry that weight instead.
- Model choices are measured, not assumed. Re-run `scripts/smoke_llm.py` before
  changing any model in `.env`, and record the numbers in `docs/ADR.md`.

---

## 7. Token discipline

This is the graded requirement ("нельзя просто отправлять целые веб-страницы в контекст").
Every change must respect:

1. **Snapshot budget: 4000 tokens.** If a page produces more, tighten filtering
   (viewport-only, collapse repeated siblings, drop non-interactive leaves) — never
   just truncate mid-structure.
2. **Delta by default.** After the first snapshot of a page, send only what changed.
3. **History compaction.** Keep the last 3 `PageState`s verbatim; replace older ones
   with a one-line summary of what happened at that step.
4. **Heavy reading goes to the sub-agent.** `read_page` on a long article is answered
   by the extractor sub-agent on the cheap model; only its structured result enters
   the main context.
5. **Hard caps.** `MAX_STEPS` and `MAX_TASK_INPUT_TOKENS` abort a runaway task.

Any PR that raises average tokens-per-step needs a note in `docs/ADR.md`.

---

## 8. Running things

Chrome must be started separately, with a debugging port and the user's real profile,
so existing logins persist:

```powershell
./scripts/launch_chrome.ps1
```

Then:

The environment is `uv`-managed (system Python 3.14 has no pip; deps target 3.12):

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -e ".[dev]"
```

Always invoke through the venv — `.venv/Scripts/python.exe` on Windows:

```bash
.venv/Scripts/python.exe -m agent.main --ui          # web panel on :8000
.venv/Scripts/python.exe -m agent.main --cli         # terminal REPL
.venv/Scripts/python.exe -m agent.main --task "..."  # one-shot
.venv/Scripts/python.exe evals/run.py                # eval suite
.venv/Scripts/python.exe -m ruff check src scripts   # lint (must be clean)

python scripts/smoke_llm.py                          # raw HTTP, stdlib only
.venv/Scripts/python.exe scripts/smoke_router.py     # end-to-end через agent.llm
.venv/Scripts/python.exe scripts/check_provider.py   # приёмка эндпоинта (~40k токенов)
```

Two smoke scripts on purpose: `smoke_llm.py` has no dependencies and answers "is the
provider alive"; `smoke_router.py` exercises the real config → router → provider path
including the fallback chain. Run the second one after any change under `llm/`.

`check_provider.py` is a different question: not "does it answer" but "is it really
Anthropic". It costs real tokens, so run it once per new key, not routinely — it
detects a dead prefix cache, an ignored `max_tokens`, a foreign injected system
prompt, and invented `usage` numbers. See `docs/PROVIDERS.md`.

Never launch a headless browser. The assignment requires a visible one.

---

## 9. Things not to do

- Do not create files not described in §4 without updating this document.
- Do not add a "quick fix" that special-cases a website. Fix the snapshot layer or the
  prompt instead — those generalise, and generality is what is being graded.
- Do not commit `.env`, `runs/`, cookies, screenshots, or anything from
  a real mailbox / hh.ru profile. The repository is **public**.
- Do not paste raw page dumps or full run logs into an AI chat while developing.
  Grep the JSONL log instead. One snapshot is ~5–15k tokens.
- Do not silently widen scope. The deadline is fixed; see `docs/ROADMAP.md` for what
  is in and what is explicitly cut.

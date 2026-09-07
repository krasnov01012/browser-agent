"""Управление настоящим Chrome пользователя.

Браузер запускается отдельно (scripts/launch_chrome.ps1) с портом отладки
и своим профилем, агент к нему присоединяется. Так закрываются сразу три
требования: программное управление, persistent sessions и видимое окно —
а заодно снимается вопрос антибот-защиты, потому что это настоящий браузер
с настоящей историей.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from playwright.async_api import (
    Browser,
    BrowserContext,
    Dialog,
    Page,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)

from ..config import Settings
from .refs import RefRegistry
from .snapshot import Element, PageState, TabInfo, capture
from .stability import STABILITY_JS, wait_until_settled

log = logging.getLogger(__name__)

# Синтетические ref для нативных диалогов. Это возможность браузера,
# а не знание о каком-либо сайте: диалог перекрывает страницу целиком,
# и агент должен иметь возможность на него ответить.
DIALOG_ACCEPT = "dlg_ok"
DIALOG_DISMISS = "dlg_cancel"


class BrowserUnavailable(RuntimeError):
    """Chrome не запущен или не слушает порт отладки."""


@dataclass(slots=True)
class PendingDialog:
    dialog: Dialog
    kind: str
    message: str


class BrowserController:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._dialog: PendingDialog | None = None
        self.refs = RefRegistry()

    # ── жизненный цикл ───────────────────────────────────────────────

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        try:
            endpoint = await self._endpoint()
            self._browser = await self._playwright.chromium.connect_over_cdp(endpoint)
        except BrowserUnavailable:
            await self._shutdown_playwright()
            raise
        except PlaywrightError as e:
            await self._shutdown_playwright()
            raise BrowserUnavailable(
                f"не удалось подключиться к Chrome на {self._settings.cdp_url}. "
                f"Запустите его: powershell -ExecutionPolicy Bypass "
                f"-File scripts/launch_chrome.ps1 ({e})"
            ) from e

        contexts = self._browser.contexts
        if not contexts:
            raise BrowserUnavailable("Chrome подключён, но не имеет открытых контекстов")
        self._context = contexts[0]

        # Детектор покоя должен встать до скриптов страницы.
        await self._context.add_init_script(STABILITY_JS)
        self._context.on("page", self._on_new_page)

        pages = [p for p in self._context.pages if not p.is_closed()]
        self._page = pages[0] if pages else await self._context.new_page()
        for page in pages:
            self._attach(page)

        log.info("подключён к Chrome, вкладок: %d", len(pages))

    async def _endpoint(self) -> str:
        """Адрес для connect_over_cdp.

        Локальный Chrome отдаётся Playwright как есть. Но если браузер на
        другом хосте — так бывает, когда агент в контейнере, а Chrome на
        машине пользователя, — Playwright сначала запрашивает /json/version,
        а Chrome отвергает такой запрос: он требует, чтобы заголовок Host был
        localhost. Поэтому спрашиваем сами, подменив Host, и подключаемся
        сразу по ws://, минуя проверку.

        Той же проверке подчиняется и сам WebSocket, причём подмена заголовка
        там уже недоступна — его формирует Playwright. Chrome принимает Host
        либо `localhost`, либо IP-адрес, поэтому имя хоста в адресе заменяется
        на разрешённый IP: `host.docker.internal` он отвергает, `192.168.65.2` —
        принимает (docs/ADR.md ADR-026).
        """
        url = self._settings.cdp_url
        parts = urlparse(url)
        host, port = parts.hostname or "", parts.port or 9222
        if host in {"localhost", "127.0.0.1", "::1", ""}:
            return url

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{url}/json/version", headers={"Host": f"localhost:{port}"}
                )
                response.raise_for_status()
                ws = str(response.json()["webSocketDebuggerUrl"])
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise BrowserUnavailable(
                f"Chrome на {url} не ответил на запрос точки отладки ({e}). "
                f"Он должен быть запущен с --remote-debugging-address=0.0.0.0"
            ) from e

        # Chrome возвращает адрес с localhost внутри себя — подставляем реальный
        # хост, но обязательно в виде IP: имя он в заголовке Host не примет.
        return re.sub(r"^ws://[^/]+", f"ws://{await _ip_of(host)}:{port}", ws)

    async def close(self) -> None:
        # Браузер пользователя не закрываем — только отсоединяемся.
        if self._browser is not None:
            with contextlib.suppress(PlaywrightError):
                await self._browser.close()
        await self._shutdown_playwright()

    async def _shutdown_playwright(self) -> None:
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    # ── события ──────────────────────────────────────────────────────

    def _on_new_page(self, page: Page) -> None:
        log.info("открылась новая вкладка: %s", page.url)
        self._attach(page)

    def _attach(self, page: Page) -> None:
        page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog: Dialog) -> None:
        # Намеренно не закрываем автоматически: текст диалога может быть
        # частью задачи. Он уйдёт в снапшот, решение примет агент.
        self._dialog = PendingDialog(dialog=dialog, kind=dialog.type, message=dialog.message)
        log.info("диалог %s: %s", dialog.type, dialog.message[:120])

    # ── доступ к состоянию ───────────────────────────────────────────

    @property
    def page(self) -> Page:
        if self._page is None or self._page.is_closed():
            pages = self.pages
            if not pages:
                raise BrowserUnavailable("не осталось открытых вкладок")
            self._page = pages[0]
        return self._page

    async def ensure_page(self) -> Page:
        """Как `page`, но пустой браузер не обрывает задачу, а получает вкладку.

        Последняя вкладка исчезает не только по вине агента: её закрывает сам
        сайт, роняет вылетевший рендерер, закрывает пользователь. Прогон
        `vacancies` оборвался на пятнадцатом шаге с «не осталось открытых
        вкладок» — вся работа до этого была потеряна на пустом месте. Пока
        соединение с браузером живо, восстановиться можно: новая вкладка стоит
        одного вызова, а куки и логины живут в профиле, а не во вкладках.
        """
        if self._context is not None and not self.pages:
            log.info("вкладок не осталось — открываем новую")
            try:
                self._page = await self._context.new_page()
            except PlaywrightError as e:
                # Вкладок нет и новую не открыть — значит, закончились не вкладки,
                # а сам браузер: его закрыли, он обновился или соединение оборвалось.
                # Ошибку Playwright здесь нельзя выпускать наружу как есть: выше её
                # никто не ждёт, и падение уносит весь набор замеров вместе с уже
                # пройденными задачами (docs/ADR.md ADR-031).
                raise BrowserUnavailable(f"соединение с Chrome потеряно ({e})") from e
            self._attach(self._page)
            return self._page
        return self.page

    @property
    def connected(self) -> bool:
        """Жив ли ещё браузер на том конце CDP."""
        return self._browser is not None and self._browser.is_connected()

    @property
    def pages(self) -> list[Page]:
        if self._context is None:
            return []
        return [p for p in self._context.pages if not p.is_closed()]

    def tabs(self) -> list[TabInfo]:
        active = self._page
        return [
            TabInfo(index=i, title=_title_of(p), url=p.url, active=p is active)
            for i, p in enumerate(self.pages)
        ]

    # ── навигация ────────────────────────────────────────────────────

    async def goto(self, url: str) -> None:
        page = await self.ensure_page()
        await page.goto(url, wait_until="domcontentloaded")

    async def go_back(self) -> bool:
        """Назад по истории. True, если адрес действительно изменился.

        Ждать `domcontentloaded` нельзя: возврат часто восстанавливается
        из bfcache, событие не приходит, и ожидание висит до таймаута.
        Ждём только фиксации перехода, а факт проверяем по адресу.
        """
        before = self.page.url
        with contextlib.suppress(PlaywrightError):
            await self.page.go_back(wait_until="commit", timeout=10_000)
        return self.page.url != before

    async def switch_tab(self, index: int) -> None:
        pages = self.pages
        if not 0 <= index < len(pages):
            raise IndexError(f"вкладки {index} нет, доступны 0..{len(pages) - 1}")
        self._page = pages[index]
        await self._page.bring_to_front()

    async def close_tab(self, index: int) -> None:
        pages = self.pages
        if not 0 <= index < len(pages):
            raise IndexError(f"вкладки {index} нет, доступны 0..{len(pages) - 1}")
        if len(pages) == 1:
            raise ValueError("нельзя закрыть единственную вкладку")
        target = pages[index]
        was_active = target is self._page
        await target.close()
        if was_active:
            self._page = self.pages[0]
            await self._page.bring_to_front()

    # ── диалоги ──────────────────────────────────────────────────────

    @property
    def pending_dialog(self) -> PendingDialog | None:
        return self._dialog

    async def resolve_dialog(self, *, accept: bool, text: str = "") -> str:
        pending = self._dialog
        if pending is None:
            raise ValueError("сейчас нет открытого диалога")
        self._dialog = None
        try:
            if accept:
                await pending.dialog.accept(text)
                return f"Диалог принят: {pending.message[:100]}"
            await pending.dialog.dismiss()
            return f"Диалог отклонён: {pending.message[:100]}"
        except PlaywrightError as e:
            return f"Диалог уже закрылся сам ({e})"

    # ── снимок состояния ─────────────────────────────────────────────

    async def settle(self) -> object:
        return await wait_until_settled(
            self.page,
            quiet_ms=self._settings.dom_settle_ms,
            timeout_ms=self._settings.dom_settle_timeout_ms,
        )

    async def snapshot(self, *, wait: bool = True) -> PageState:
        # Снапшот снимается перед каждым шагом — это и есть то место, где
        # пропажу последней вкладки замечают раньше всего.
        page = await self.ensure_page()
        stability = await self.settle() if wait else None
        state = await capture(
            page,
            self.refs,
            tabs=self.tabs(),
            stability=stability,
        )
        self._inject_dialog(state)
        return state

    def _inject_dialog(self, state: PageState) -> None:
        """Нативный диалог блокирует страницу — показываем его первым."""
        pending = self._dialog
        if pending is None:
            return

        state.elements.insert(
            0,
            Element(
                ref=DIALOG_ACCEPT,
                role="alertdialog",
                name=f"{pending.kind}: {pending.message}",
                landmark=True,
                sig="dialog",
            ),
        )
        state.elements.insert(
            1,
            Element(
                ref=DIALOG_DISMISS,
                role="button",
                name="Отклонить диалог",
                landmark=True,
                sig="dialog",
            ),
        )
        state.elements[0].value = "нажмите dlg_ok чтобы принять"


async def _ip_of(host: str) -> str:
    """Имя хоста -> IP. При неудаче возвращает имя как есть.

    Разрешение имени блокирующее, поэтому уходит в поток: цикл событий здесь
    обслуживает браузер, и вставать на DNS ему нельзя.
    """
    try:
        info = await asyncio.to_thread(socket.getaddrinfo, host, None, socket.AF_INET)
    except OSError:
        return host
    return str(info[0][4][0]) if info else host


def _title_of(page: Page) -> str:
    # Синхронный доступ: заголовок кэшируется Playwright, await не нужен
    # и в горячем пути дорог.
    try:
        return page.url.split("//", 1)[-1].split("/", 1)[0]
    except (IndexError, AttributeError):
        return page.url

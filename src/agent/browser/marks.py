"""Скриншот с пронумерованными рамками (Set-of-Mark).

Номера на картинке совпадают с ref текстового снапшота, поэтому после взгляда
на изображение агент кликает тем же самым `click(ref)` — второго словаря целей
не появляется.

Вызывается только по явному запросу агента: картинка стоит ~1.5k токенов
против сотен у текстового состояния.
"""

from __future__ import annotations

import base64
import logging

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page

log = logging.getLogger(__name__)

#: больше рамок на экране только мешает читать
MAX_MARKS = 60

_DRAW_JS = """(refs) => {
  const layer = document.createElement('div');
  layer.id = '__agent_marks';
  layer.style.cssText =
    'position:fixed;inset:0;z-index:2147483647;pointer-events:none';

  const reg = window.__agentRegistry;
  if (!reg) return 0;
  let drawn = 0;

  for (const ref of refs) {
    const el = reg.byRef.get(ref);
    if (!el || !el.isConnected) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (r.bottom < 0 || r.top > innerHeight) continue;

    const box = document.createElement('div');
    box.style.cssText =
      `position:absolute;left:${r.left}px;top:${r.top}px;` +
      `width:${r.width}px;height:${r.height}px;` +
      'outline:2px solid #ff2d55;outline-offset:-1px';

    const tag = document.createElement('div');
    tag.textContent = ref;
    tag.style.cssText =
      `position:absolute;left:${r.left}px;top:${Math.max(0, r.top - 14)}px;` +
      'background:#ff2d55;color:#fff;font:11px/13px monospace;' +
      'padding:0 3px;border-radius:2px;white-space:nowrap';

    layer.appendChild(box);
    layer.appendChild(tag);
    drawn++;
  }

  document.body.appendChild(layer);
  return drawn;
}"""

_CLEAR_JS = """() => {
  const layer = document.getElementById('__agent_marks');
  if (layer) layer.remove();
}"""


async def screenshot_with_marks(
    page: Page,
    refs: list[str],
    *,
    marked: bool = True,
) -> tuple[str, int]:
    """Скриншот видимой области. Возвращает (base64 PNG, число рамок)."""
    drawn = 0
    if marked and refs:
        try:
            drawn = int(await page.evaluate(_DRAW_JS, refs[:MAX_MARKS]) or 0)
        except PlaywrightError as e:
            log.debug("не удалось нарисовать рамки: %s", e)

    try:
        raw = await page.screenshot(type="png")
    except PlaywrightError as e:
        raise RuntimeError(f"скриншот не сделался: {e}") from e
    finally:
        if drawn:
            try:
                await page.evaluate(_CLEAR_JS)
            except PlaywrightError:
                log.debug("слой рамок остался на странице")

    return base64.b64encode(raw).decode("ascii"), drawn

"""Ошибки инструментов в том виде, в каком их увидит модель.

Правило: сообщение подсказывает направление, а не описывает внутренности.
Питоновский трейсбек в контексте — потраченные токены, которые ничему
не учат. Сравните:

    плохо   ToolError: element not actionable (timeout 30000ms)
    хорошо  Элемент e22 перекрыт элементом e91 («Подтвердите действие»).
            Закройте перекрывающий элемент и повторите.
"""

from __future__ import annotations


class ToolError(Exception):
    """База. Возвращается модели как результат вызова, а не как исключение."""

    #: короткий машинный ярлык — по нему цикл считает статистику ошибок
    kind = "error"

    def for_model(self) -> str:
        return str(self)


class BadArguments(ToolError):
    """Инструмент вызван с неверными или недостающими аргументами."""

    kind = "bad_arguments"

    def __init__(self, tool: str, detail: str) -> None:
        super().__init__(f"{tool}: {detail}")
        self.tool = tool
        self.detail = detail

    def for_model(self) -> str:
        return f"Инструмент {self.tool} вызван неверно: {self.detail}"


class UnknownTool(ToolError):
    kind = "unknown_tool"

    def __init__(self, name: str, available: list[str]) -> None:
        super().__init__(f"нет инструмента {name!r}")
        self.name = name
        self.available = available

    def for_model(self) -> str:
        return (
            f"Инструмента {self.name} не существует. Доступны: {', '.join(sorted(self.available))}."
        )


class NotVisible(ToolError):
    """Элемент есть, но до него не удалось добраться прокруткой."""

    kind = "not_visible"

    def __init__(self, ref: str) -> None:
        super().__init__(f"элемент {ref} недоступен")
        self.ref = ref

    def for_model(self) -> str:
        return (
            f"До элемента {self.ref} не удалось добраться прокруткой — возможно, "
            f"он скрыт свёрнутым блоком. Попробуйте другой путь к цели."
        )


class Covered(ToolError):
    """Элемент перекрыт другим — почти всегда модалкой или баннером."""

    kind = "covered"

    def __init__(self, ref: str, blocker: str) -> None:
        super().__init__(f"элемент {ref} перекрыт")
        self.ref = ref
        self.blocker = blocker

    def for_model(self) -> str:
        # Пока оверлей лежит сверху, перекрыты ВСЕ элементы под ним. Без этой
        # фразы агент перебирает соседние ref по одному и получает то же самое.
        return (
            f"Элемент {self.ref} перекрыт: {self.blocker}. Пока этот блок открыт, "
            f"клики по любым элементам под ним не сработают — перебирать другие ref "
            f"бесполезно. Сначала уберите его: нажмите Escape через press_key, либо "
            f"найдите в текущем состоянии страницы кнопку закрытия или согласия "
            f"и нажмите её. Только потом повторяйте действие."
        )


class ActionTimeout(ToolError):
    """Действие не завершилось за отведённое время."""

    kind = "timeout"

    def __init__(self, what: str) -> None:
        super().__init__(f"{what}: превышено время ожидания")
        self.what = what

    def for_model(self) -> str:
        return (
            f"Действие «{self.what}» не завершилось за отведённое время. "
            f"Страница могла зависнуть — посмотрите на её состояние и решите, "
            f"ждать или действовать иначе."
        )


class NavigationFailed(ToolError):
    kind = "navigation"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail

    def for_model(self) -> str:
        return f"Перейти не удалось: {self.detail}"


class ToolFailed(ToolError):
    """Всё прочее — с максимально конкретным текстом."""

    kind = "failed"

    def __init__(self, tool: str, detail: str) -> None:
        super().__init__(f"{tool}: {detail}")
        self.tool = tool
        self.detail = detail

    def for_model(self) -> str:
        return f"Инструмент {self.tool} не сработал: {self.detail}"

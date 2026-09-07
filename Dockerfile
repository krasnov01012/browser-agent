# Агент в контейнере, Chrome — на машине пользователя.
#
# Так и задумано: браузер должен быть настоящим и видимым, с профилем и
# логинами пользователя (docs/ADR.md ADR-002). Поэтому образ не тянет
# playwright install: браузеры внутрь не нужны, драйвер для CDP уже лежит
# в самом пакете playwright.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Слой зависимостей отдельно от кода: правка исходников не пересобирает его.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY evals ./evals
COPY scripts ./scripts

# Chrome снаружи; localhost внутри контейнера — это сам контейнер.
ENV CDP_URL=http://host.docker.internal:9222 \
    UI_HOST=0.0.0.0 \
    UI_PORT=8000 \
    LOG_DIR=/app/runs \
    MEMORY_DIR=/app/memory

EXPOSE 8000

CMD ["browser-agent", "--ui"]

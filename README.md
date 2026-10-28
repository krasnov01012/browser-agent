# Krasnoff Development — сайт студии

Сайт независимой студии заказной разработки ПО (RU/EN): тёмный Hero с 3D-знаком
Architectural K, редакционный каталог услуг, кейсы собственных продуктов Seshat и MARK,
подход и процесс, единый приём заявок (короткая форма + бриф проекта в 4 шага).

**Стек:** Astro 7 (статическая сборка) · TypeScript · Three.js · Lenis · собственный CSS на токенах ·
Geist + IBM Plex Mono (self-hosted).

```bash
nvm use            # Node 24 LTS (Astro 7 требует ≥ 22.23.4)
npm install
npm run dev        # http://localhost:4321/ru/  ·  /en/
npm run build && npm run preview
npm run qa:shots   # визуальная проверка → qa/
```

Добавьте `?review` к адресу, чтобы увидеть статусы контента (черновик / предложение / плейсхолдер).

- Инструкции для AI-агентов и правила проекта — [`CLAUDE.md`](CLAUDE.md)
- Что сделано и что ждёт материалов — [`docs/STATUS.md`](docs/STATUS.md)
- Вопросы к обсуждению — [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md)
- Бриф (санитизированный) — [`docs/brief/`](docs/brief) · решения реализации — [`docs/DECISIONS.md`](docs/DECISIONS.md)

> Предварительная сборка: тексты — черновики, медиа кейсов — подписанные иллюстрации,
> приём заявок не подключён. Не для публикации до ревью владельца.

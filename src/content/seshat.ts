/*
 * Кейс Seshat v1.2 — тексты RU/EN (черновики из SESHAT_CASE_DESIGN_V12, см. docs/brief/04_CASES.md).
 * Цифры тестов и наблюдений НЕ выводятся до проверки по CI/репозиторию продукта.
 */
import type { Locale } from '@/i18n';

const ru = {
  meta: {
    title: 'Seshat — AI-планировщик и инженерный кейс | Krasnoff Development',
    description:
      'Seshat — персональная система планирования: запросы обычным языком, детерминированная календарная логика, подтверждения и надёжные напоминания в Telegram.',
  },
  crumb: ['Работы', 'Seshat'],
  hero: {
    kicker: 'Независимый продукт / AI и разработка ПО',
    title: 'Seshat',
    claim: 'Время под контролем.',
    deck: 'Персональная система планирования: понятные команды на обычном языке, точная работа с расписанием и надёжная доставка напоминаний.',
    cta1: 'Изучить систему',
    cta2: 'Обсудить похожий проект',
    meta: ['Telegram-first', 'API-first', 'Production-развёртывание'],
  },
  challenge: {
    index: '02 / Задача',
    titleLines: ['Удобно говорить.', 'Важно точно', 'планировать.'],
    body: 'Фраза «перенеси встречу на следующую пятницу» выглядит простой, пока система не сталкивается с часовыми поясами, повторяющимися событиями и неоднозначными датами. В Seshat понимание запроса и изменение расписания разделены: модель помогает разобрать формулировку, а проверки, календарная арифметика и подтверждение остаются в программной логике.',
    split: [
      { tag: '01 / Понимание', title: 'Разобрать запрос', text: 'Быстрый парсер и LLM извлекают намерение и поля: что, когда, как часто.' },
      { tag: '02 / Исполнение', title: 'Проверить и подтвердить', text: 'Даты, повторения, часовые пояса и конфликты считает код. Изменение — только после подтверждения.' },
    ],
  },
  experience: {
    index: '03 / Опыт продукта',
    titleLines: ['Планируй.', 'Адаптируй.', 'Анализируй.'],
    tabs: [
      {
        id: 'create',
        label: 'Создать',
        caption: 'Планируйте естественно',
        message: 'Каждый понедельник в 19:00 тренировка',
        steps: ['Сообщение обычным языком', 'Разбор: рутина, еженедельно, Пн 19:00', 'Карточка подтверждения', 'Рутина сохранена'],
      },
      {
        id: 'adapt',
        label: 'Изменить',
        caption: 'Меняйте без хаоса',
        message: 'Перенеси стоматолога на завтра в 15:00',
        steps: ['Команда на изменение', 'Дата и время вычислены кодом', 'Предпросмотр «было → стало»', 'Событие обновлено, доступна отмена'],
      },
      {
        id: 'reflect',
        label: 'Итоги',
        caption: 'Подводите итоги осмысленно',
        message: 'Сегодня закончил проект и сходил на тренировку',
        steps: ['Вечерний вопрос «Что успел сегодня?»', 'Факты извлечены из ответа', 'Сопоставление с расписанием', 'Итог дня без «токсичной мотивации»'],
      },
    ],
    pending: 'Демо-запись готовится — здесь будет реальный Telegram на демо-профиле',
    stepsLabel: 'Сценарий',
  },
  architecture: {
    index: '04 / Архитектура',
    titleLines: ['Интеллект', 'с чёткими', 'правилами.'],
    deck: 'AI помогает понять намерение. Изменения в расписании проходят проверку и подтверждение. При недоступности внешнего провайдера система использует резервные способы обработки.',
    views: { product: 'Продукт', engineering: 'Инженерия' },
    note: 'Упрощённая схема: реальная обработка ветвится, не каждый запрос доходит до LLM.',
    product: [
      { title: 'Сообщение', text: 'Запрос обычным языком в Telegram' },
      { title: 'Понимание', text: 'Быстрый разбор → LLM с защитой → резервный путь' },
      { title: 'Правила', text: 'Даты, повторения, часовые пояса, конфликты' },
      { title: 'Подтверждение', text: 'Карточка «до/после», сохранение, отмена' },
      { title: 'Напоминания и итоги', text: 'Планировщик, тихие часы, разборы дня' },
    ],
    engineering: [
      { title: 'Адаптеры', text: 'Aiogram 3 · FastAPI — тонкие слои над доменом' },
      { title: 'Разбор', text: 'Детерминированный парсер · LLM (tool-use / JSON Schema) · FSM без AI' },
      { title: 'Домен', text: 'RRULE (RFC 5545) · zoneinfo / DST · без зависимостей от фреймворков' },
      { title: 'Данные', text: 'PostgreSQL 16 · SQLAlchemy 2 async · advisory locks · журнал' },
      { title: 'Фон', text: 'Планировщик · watchdog · идемпотентные подтверждения' },
    ],
  },
  engineering: {
    index: '05 / Инженерия',
    titleLines: ['Надёжность', 'на уровне', 'архитектуры.'],
    rows: [
      { title: 'Надёжность', summary: 'Контроль фоновых задач, идемпотентные подтверждения, координация процессов.', detail: 'Сторож (watchdog) следит за циклами планировщика и сообщает о зависании; повторное нажатие кнопки подтверждения не создаёт дубль; бот и API координируются через блокировки в PostgreSQL.' },
      { title: 'Целостность данных', summary: 'Черновики, журнал изменений, отмена одной кнопкой, транзакции.', detail: 'Каждая карточка подтверждения хранится на сервере; любая правка сохраняет снимок «до» — изменение можно откатить.' },
      { title: 'Контролируемый деплой', summary: 'Проверка бэкапа, «аддитивные» миграции, health-check, автоматический откат.', detail: 'Перед выкладкой снимается и проверяется дамп; миграции без разрушающих операций; при провале проверок — откат с сохранением данных. Текущую схему деплоя нужно сверить перед публикацией.' },
      { title: 'Тестирование', summary: 'Тесты на реальной PostgreSQL, крайние случаи дат и часовых поясов, quality gates.', detail: 'Количество тестов будет указано только после сверки с актуальным CI.' },
    ],
  },
  outcome: {
    index: '06 / Статус',
    titleLines: ['Сделано.', 'Запущено.', 'Развивается.'],
    lead: 'Текущая функциональность указана по техническому описанию владельца; перед публикацией сверяется с актуальным репозиторием.',
    available: {
      title: 'Работает',
      items: ['Интерфейс в Telegram', 'Задачи, события, рутины и цели на период', 'Гибридная обработка языка с резервными путями', 'Напоминания с тихими часами', 'Итоги дня, недели, месяца', 'API и production-развёртывание'],
    },
    progress: {
      title: 'В разработке / не включено',
      items: ['Полноценный веб-клиент (SPA)', 'Синхронизация Google Calendar в production', 'Голосовой ввод', 'Долговременная память и глобальные цели («Горизонт 3»)'],
    },
  },
  next: {
    label: '07 / Следующий кейс',
    name: 'Mark',
    teaser: 'Персональный AI-агент поиска и сопоставления вакансий.',
    ctaTitle: 'Нужна похожая система?',
    ctaText: 'Разработка индивидуальных программных решений и сопровождение после запуска.',
    cta: 'Обсудить похожий проект',
  },
};

type CaseSeshat = typeof ru;

const en: CaseSeshat = {
  meta: {
    title: 'Seshat — AI Planning System Case Study | Krasnoff Development',
    description:
      'Seshat is a personal planning system: natural-language requests, deterministic scheduling logic, confirmations and dependable reminders in Telegram.',
  },
  crumb: ['Work', 'Seshat'],
  hero: {
    kicker: 'Independent product / AI & software engineering',
    title: 'Seshat',
    claim: 'Time, engineered.',
    deck: 'A personal planning system combining natural-language requests, precise scheduling logic and dependable reminders.',
    cta1: 'Explore the system',
    cta2: 'Discuss a similar project',
    meta: ['Telegram-first', 'API-first', 'Production deployment'],
  },
  challenge: {
    index: '02 / The challenge',
    titleLines: ['Natural language.', 'Precise', 'execution.'],
    body: '“Move my meeting to next Friday” sounds simple until time zones, recurring events and ambiguous dates come into play. Seshat separates interpretation from execution: AI helps structure the request while deterministic code validates calendar operations and asks for confirmation.',
    split: [
      { tag: '01 / Understand', title: 'Interpret the request', text: 'A fast parser and LLMs extract intent and fields: what, when, how often.' },
      { tag: '02 / Execute', title: 'Validate and confirm', text: 'Code resolves dates, recurrence, time zones and conflicts. Nothing changes without confirmation.' },
    ],
  },
  experience: {
    index: '03 / Product experience',
    titleLines: ['Plan.', 'Adapt.', 'Reflect.'],
    tabs: [
      {
        id: 'create',
        label: 'Create',
        caption: 'Plan naturally',
        message: 'Workout every Monday at 7 pm',
        steps: ['A message in plain language', 'Parsed: routine, weekly, Mon 19:00', 'Confirmation card', 'Routine saved'],
      },
      {
        id: 'adapt',
        label: 'Adapt',
        caption: 'Change with control',
        message: 'Move the dentist to tomorrow at 3 pm',
        steps: ['A change request', 'Date and time resolved by code', '“Before → after” preview', 'Event updated, undo available'],
      },
      {
        id: 'reflect',
        label: 'Reflect',
        caption: 'Reflect on what got done',
        message: 'Finished the project today and went to the gym',
        steps: ['Evening prompt: “What did you get done?”', 'Facts extracted from the reply', 'Matched against the schedule', 'A daily review without guilt-tripping'],
      },
    ],
    pending: 'Demo footage pending — real Telegram on a demo profile will appear here',
    stepsLabel: 'Scenario',
  },
  architecture: {
    index: '04 / Architecture',
    titleLines: ['Intelligence', 'with', 'guardrails.'],
    deck: 'AI helps interpret intent. Calendar changes go through validation and confirmation. Fallback paths keep key interactions usable when external AI services are unavailable.',
    views: { product: 'Product view', engineering: 'Engineering view' },
    note: 'Simplified diagram: real processing branches, and not every request reaches an LLM.',
    product: [
      { title: 'Message', text: 'A plain-language request in Telegram' },
      { title: 'Understanding', text: 'Fast parse → guarded LLM → fallback path' },
      { title: 'Rules', text: 'Dates, recurrence, time zones, conflicts' },
      { title: 'Confirmation', text: '“Before/after” card, persistence, undo' },
      { title: 'Reminders & reviews', text: 'Scheduler, quiet hours, daily reviews' },
    ],
    engineering: [
      { title: 'Adapters', text: 'Aiogram 3 · FastAPI — thin layers over the domain' },
      { title: 'Parsing', text: 'Deterministic parser · LLM (tool use / JSON Schema) · AI-free FSM' },
      { title: 'Domain', text: 'RRULE (RFC 5545) · zoneinfo / DST · framework-independent' },
      { title: 'Data', text: 'PostgreSQL 16 · SQLAlchemy 2 async · advisory locks · audit log' },
      { title: 'Background', text: 'Scheduler · watchdog · idempotent confirmations' },
    ],
  },
  engineering: {
    index: '05 / Engineering',
    titleLines: ['Reliability', 'by', 'design.'],
    rows: [
      { title: 'Reliability', summary: 'Background job supervision, idempotent confirmations, process coordination.', detail: 'A watchdog monitors the scheduler loops and alerts on stalls; pressing a confirmation twice never creates a duplicate; the bot and the API coordinate through PostgreSQL locks.' },
      { title: 'Data integrity', summary: 'Drafts, audit log, one-tap undo, transactional operations.', detail: 'Every confirmation card is stored server-side; each edit keeps a “before” snapshot so the change can be rolled back.' },
      { title: 'Safe deployment', summary: 'Backup validation, additive migrations, health checks, automatic rollback.', detail: 'A verified dump is taken before release; migrations avoid destructive operations; failed health checks roll back while preserving data. The current deployment flow is to be verified before publication.' },
      { title: 'Testing', summary: 'Tests on a real PostgreSQL, date and time-zone edge cases, quality gates.', detail: 'The test count will be published only after it is verified against the current CI.' },
    ],
  },
  outcome: {
    index: '06 / Status',
    titleLines: ['Built.', 'Deployed.', 'Evolving.'],
    lead: 'Current functionality is described from the owner’s technical summary and is verified against the live repository before publication.',
    available: {
      title: 'Working',
      items: ['Telegram interface', 'Tasks, events, routines and period goals', 'Hybrid language processing with fallbacks', 'Reminders with quiet hours', 'Daily, weekly and monthly reviews', 'API and production deployment'],
    },
    progress: {
      title: 'In progress / not enabled',
      items: ['Full web client (SPA)', 'Google Calendar sync in production', 'Voice input', 'Long-term memory and global goals (“Horizon 3”)'],
    },
  },
  next: {
    label: '07 / Next case',
    name: 'Mark',
    teaser: 'A personal AI agent for job discovery and matching.',
    ctaTitle: 'Need a system like this?',
    ctaText: 'Custom software development and support after launch.',
    cta: 'Discuss a similar project',
  },
};

export const seshat: Record<Locale, CaseSeshat> = { ru, en };

/*
 * Кейс MARK v1.2 — тексты RU/EN (черновики из MARK_CASE_DESIGN_V12, см. docs/brief/04_CASES.md).
 * Только подтверждённая владельцем форма процесса; никаких чисел, процентов и приватных фильтров.
 */
import type { Locale } from '@/i18n';

const ru = {
  meta: {
    title: 'MARK — AI-агент подбора вакансий | Krasnoff Development',
    description:
      'MARK — персональный AI-агент: сбор вакансий из HeadHunter и Habr Career, фильтрация по правилам, сопоставление с профилем и доставка результатов через Telegram.',
  },
  crumb: ['Работы', 'Mark'],
  hero: {
    kicker: 'Независимый продукт / Автоматизация и AI',
    title: 'Mark',
    claim: 'Сигнал вместо шума.',
    deck: 'Персональный AI-агент, который собирает вакансии из нескольких источников, отсеивает неподходящие по заданным правилам и помогает находить релевантные предложения через Telegram.',
    cta1: 'Посмотреть принцип работы',
    cta2: 'Обсудить похожую задачу',
    band: ['Автоматизация', 'API', 'LLM', 'Telegram'],
  },
  challenge: {
    index: '02 / Задача',
    titleLines: ['Вакансий много.', 'Подходящих —', 'не все.'],
    body: 'Источники вакансий показывают разные форматы данных и много предложений, которые не соответствуют условиям конкретного кандидата. MARK выстраивает последовательность отбора: сначала прозрачные правила, затем оценка содержания вакансии в контексте персонального профиля.',
    points: [
      { title: 'Разные источники', text: 'Вакансии приходят с отдельных площадок и в разных форматах.' },
      { title: 'Много шума', text: 'Не каждое предложение соответствует реальным условиям и требованиям.' },
      { title: 'Нужен контекст', text: 'Релевантность зависит от навыков, задач и персонального профиля.' },
    ],
    band: ['Сырой поток', 'Отбор по правилам', 'Приватная доставка'],
  },
  pipeline: {
    index: '03 / Конвейер',
    titleLines: ['Пять этапов —', 'от источников', 'до сообщения.'],
    lead: 'Выберите этап, чтобы увидеть, что на нём происходит. Схема концептуальная: реальные поля, правила и профиль не публикуются.',
    stageLabel: 'Этап',
    stages: [
      { id: 'capture', code: 'CAPTURE', title: 'Источники', text: 'Новые вакансии поступают из двух публичных источников: HeadHunter API и RSS Habr Career.', viz: 'sources' },
      { id: 'normalize', code: 'NORMALIZE', title: 'Единый формат', text: 'Записи из разных источников приводятся к сопоставимым полям: роль, место, формат работы, описание.', viz: 'normalize' },
      { id: 'rules', code: 'RULES', title: 'Проверка условий', text: 'Явные ограничения кандидата проверяются детерминированными правилами — прозрачно и воспроизводимо.', viz: 'rules' },
      { id: 'match', code: 'AI MATCH', title: 'AI-сопоставление', text: 'Оставшиеся вакансии LLM читает в контексте приватного профиля навыков. Оценка — подсказка, а не решение.', viz: 'match' },
      { id: 'deliver', code: 'DELIVER', title: 'Результат в Telegram', text: 'Отобранные вакансии приходят в Telegram — привычный канал, без отдельного интерфейса.', viz: 'deliver' },
    ],
    synthetic: 'Синтетический пример — не интерфейс продукта',
  },
  decision: {
    index: '04 / Логика решений',
    titleLines: ['Правила', 'перед AI.'],
    deck: 'Чёткие ограничения проверяются кодом. AI подключается там, где нужно понять содержание вакансии и сопоставить его с профилем.',
    panels: [
      { tag: '01 / Детерминированно', title: 'Прозрачная фильтрация', text: 'Формат работы, расположение и другие заданные требования проверяются правилами, которые можно прочитать и изменить.', rule: 'IF requirements pass → CONTINUE' },
      { tag: '02 / Вероятностно', title: 'Чтение содержания', text: 'Описание вакансии сопоставляется с приватным карьерным профилем. Модель советует — решение остаётся за человеком.', rule: 'job content + private context → REVIEW' },
    ],
    views: { product: 'Продуктовый взгляд', engineering: 'Инженерный взгляд' },
    product: 'Сначала отсеиваем неподходящее по чётким условиям, затем изучаем оставшиеся предложения в контексте профиля. Результат приходит в привычный канал — Telegram.',
    engineering: 'Адаптеры источников → нормализация записей → детерминированные правила → LLM-оценка с приватным профилем → доставка в Telegram. Провайдер модели, дедупликация, повторы и расписание запусков указываются только после аудита кода.',
  },
  output: {
    index: '05 / Результат',
    titleLines: ['От данных —', 'к действию.'],
    lead: 'Итог работы MARK — сообщение в Telegram с отобранными вакансиями. Здесь появится обезличенная запись реального прогона на демо-аккаунте.',
    flow: ['Получено', 'Проверено', 'Доставлено'],
    pendingTitle: 'Запись ещё не добавлена',
    pendingText: 'Здесь будет настоящая демонстрация Telegram-уведомлений — без имён, работодателей и персональных данных.',
  },
  engineering: {
    index: '06 / Инженерия и статус',
    titleLines: ['Честно', 'о состоянии.'],
    rows: [
      { title: 'Источники и адаптеры', summary: 'HeadHunter API и Habr Career RSS.', detail: 'Актуальная авторизация и условия использования источников проверяются перед публикацией.' },
      { title: 'Детерминированная фильтрация', summary: 'Явные условия кандидата — до любых вызовов модели.', detail: 'Конкретные правила приватны и на сайте не раскрываются.' },
      { title: 'LLM-оценка', summary: 'Смысловое сопоставление вакансии с приватным профилем.', detail: 'Провайдер, метод оценки и резервные пути указываются только после проверки кода.' },
      { title: 'Доставка и эксплуатация', summary: 'Уведомления с результатами в Telegram.', detail: 'Дедупликация, повторы, расписание и мониторинг — до проверки не заявляются.' },
    ],
    status: {
      implemented: { title: 'Работает (по описанию владельца)', items: ['Личный конвейер', 'HH API + Habr RSS', 'Детерминированная фильтрация', 'LLM-сопоставление', 'Доставка в Telegram'] },
      verify: { title: 'Проверить / в разработке', items: ['Детали развёртывания', 'Хранение и дедупликация', 'Резервные пути', 'Метрики качества'] },
      not: { title: 'Не заявляется', items: ['Публичный SaaS', 'Автоотклики на вакансии', 'Охват всех источников', 'Измеренная точность подбора'] },
    },
  },
  next: {
    label: '07 / Следующий кейс',
    name: 'Seshat',
    teaser: 'Персональная система планирования с детерминированной календарной логикой.',
    ctaTitle: 'Другой продукт. Та же инженерная основа.',
    ctaText: 'Автоматизация, интеграции данных и AI там, где он действительно нужен.',
    cta: 'Обсудить свой проект',
  },
};

type CaseMark = typeof ru;

const en: CaseMark = {
  meta: {
    title: 'MARK — AI Job Discovery Agent Case Study | Krasnoff Development',
    description:
      'MARK is a personal AI job search agent combining vacancy ingestion, deterministic rules, LLM-assisted matching and Telegram delivery.',
  },
  crumb: ['Work', 'Mark'],
  hero: {
    kicker: 'Independent product / Automation & AI',
    title: 'Mark',
    claim: 'Signal over noise.',
    deck: 'A personal AI job discovery agent that pulls vacancies from multiple sources, applies rule-based filters and delivers profile-aware selections through Telegram.',
    cta1: 'Explore the workflow',
    cta2: 'Discuss a similar project',
    band: ['Automation', 'API', 'LLM', 'Telegram'],
  },
  challenge: {
    index: '02 / The challenge',
    titleLines: ['More listings.', 'Not always', 'more fit.'],
    body: 'Job listings arrive in different formats, and many fail a candidate’s requirements. MARK introduces a structured selection process: explicit rules first, then an AI-assisted reading of the vacancy against a private profile.',
    points: [
      { title: 'Different sources', text: 'Vacancies come from separate platforms in different formats.' },
      { title: 'A lot of noise', text: 'Not every listing matches real constraints and requirements.' },
      { title: 'Context matters', text: 'Relevance depends on skills, goals and a personal profile.' },
    ],
    band: ['Raw input', 'Ruled selection', 'Private delivery'],
  },
  pipeline: {
    index: '03 / Pipeline',
    titleLines: ['Five stages —', 'from sources', 'to a message.'],
    lead: 'Select a stage to see what happens there. The diagram is conceptual: real fields, rules and the profile are not published.',
    stageLabel: 'Stage',
    stages: [
      { id: 'capture', code: 'CAPTURE', title: 'Sources', text: 'New vacancies arrive from two public sources: the HeadHunter API and the Habr Career RSS feed.', viz: 'sources' },
      { id: 'normalize', code: 'NORMALIZE', title: 'Unified format', text: 'Records from different sources are mapped to comparable fields: role, location, work mode, description.', viz: 'normalize' },
      { id: 'rules', code: 'RULES', title: 'Explicit rules', text: 'The candidate’s explicit constraints are checked by deterministic rules — transparent and reproducible.', viz: 'rules' },
      { id: 'match', code: 'AI MATCH', title: 'AI-assisted fit', text: 'An LLM reads the remaining vacancies in the context of a private skills profile. The assessment advises; it does not decide.', viz: 'match' },
      { id: 'deliver', code: 'DELIVER', title: 'Telegram delivery', text: 'Selected vacancies arrive in Telegram — a familiar channel, no separate interface.', viz: 'deliver' },
    ],
    synthetic: 'Synthetic example — not product UI',
  },
  decision: {
    index: '04 / Decision logic',
    titleLines: ['Rules', 'before AI.'],
    deck: 'Explicit constraints run through deterministic checks. AI is used where the content of a job needs more nuanced interpretation against a private profile.',
    panels: [
      { tag: '01 / Deterministic', title: 'Transparent filtering', text: 'Work mode, location and other stated requirements are checked by rules you can read and change.', rule: 'IF requirements pass → CONTINUE' },
      { tag: '02 / Probabilistic', title: 'Reading the content', text: 'The job description is compared with a private career profile. The model advises — the decision stays with a person.', rule: 'job content + private context → REVIEW' },
    ],
    views: { product: 'Product view', engineering: 'Engineering view' },
    product: 'First filter out what fails clear constraints, then study the remaining listings in the context of the profile. The result arrives in a familiar channel — Telegram.',
    engineering: 'Source adapters → record normalisation → deterministic rules → LLM assessment with a private profile → Telegram delivery. Model provider, deduplication, retries and run schedule are stated only after a code audit.',
  },
  output: {
    index: '05 / Output',
    titleLines: ['From data', 'to action.'],
    lead: 'MARK’s result is a Telegram message with selected vacancies. A sanitised recording of a real run on a demo account will appear here.',
    flow: ['Received', 'Reviewed', 'Delivered'],
    pendingTitle: 'Recording not added yet',
    pendingText: 'A real demonstration of Telegram notifications will appear here — without names, employers or personal data.',
  },
  engineering: {
    index: '06 / Engineering & status',
    titleLines: ['An honest', 'status.'],
    rows: [
      { title: 'Sources & adapters', summary: 'HeadHunter API and Habr Career RSS.', detail: 'Current authorisation and source terms of use are verified before publication.' },
      { title: 'Deterministic pre-filtering', summary: 'Explicit candidate constraints — before any model call.', detail: 'The actual rules are private and not disclosed on the site.' },
      { title: 'LLM evaluation', summary: 'Semantic matching of a vacancy against a private profile.', detail: 'Provider, evaluation method and fallbacks are stated only after code verification.' },
      { title: 'Delivery & operations', summary: 'Result notifications in Telegram.', detail: 'Deduplication, retries, schedule and monitoring are not claimed until verified.' },
    ],
    status: {
      implemented: { title: 'Working (per owner’s report)', items: ['Personal pipeline', 'HH API + Habr RSS', 'Deterministic filtering', 'LLM matching', 'Telegram delivery'] },
      verify: { title: 'To verify / in development', items: ['Deployment details', 'Storage and deduplication', 'Fallback paths', 'Quality metrics'] },
      not: { title: 'Not claimed', items: ['Public SaaS', 'Auto-applying to vacancies', 'Coverage of every source', 'Measured matching accuracy'] },
    },
  },
  next: {
    label: '07 / Next case',
    name: 'Seshat',
    teaser: 'A personal planning system with deterministic scheduling logic.',
    ctaTitle: 'Different product. Same engineering mindset.',
    ctaText: 'Automation, data integration and AI where it genuinely helps.',
    cta: 'Discuss your project',
  },
};

export const mark: Record<Locale, CaseMark> = { ru, en };

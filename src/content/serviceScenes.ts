/**
 * Подписи внутри сцен услуг (src/components/home/services/scenes/*). RU — по-русски, EN — по-английски;
 * общепринятые аббревиатуры (API, CSV, CRM, LLM, HTTPS) одинаковы в обоих языках.
 * Длина ограничена местом в схеме: моноширинный 8.5 px ≈ 5.8 единицы на знак (поля — в комментариях).
 */
import type { Locale } from '@/i18n';

const ru = {
  web: {
    hero: 'ПЕРВЫЙ ЭКРАН', // ≤ 40 знаков
    card: 'КАРТОЧКА', // ≤ 12
    url: 'https://product.app',
    live: 'ОНЛАЙН', // ≤ 7
    desktop: 'КОМПЬЮТЕР · 1440', // ≤ 20
    phone: 'ТЕЛЕФОН · 390', // ≤ 14
    ship: ['СБОРКА', 'ТЕСТЫ', 'ВЫКЛАДКА'],
  },
  systems: {
    modules: ['CRM', 'АДМИНКА', 'API', 'ОТЧЁТЫ'], // ≤ 11
    roles: ['МЕНЕДЖЕР', 'ВЛАДЕЛЕЦ', 'СЕРВИС', 'ЧТЕНИЕ'], // ≤ 9
    count: 'МОДУЛИ · 4 / 4',
    core: 'ЯДРО',
    logic: 'БИЗНЕС-ЛОГИКА', // ≤ 15
    auth: 'ВХОД',
    access: 'ДОСТУП ПО РОЛЯМ',
    queue: 'ОЧЕРЕДЬ ЗАДАЧ', // ≤ 14
  },
  ai: {
    input: 'ЗАПРОС',
    model: 'LLM',
    modelNote: 'ПОНИМАЕТ ЗАДАЧУ', // ≤ 22
    checks: 'ПРОВЕРКИ',
    items: ['ФОРМАТ', 'ПРАВИЛА', 'ДОСТУПЫ'], // ≤ 9
    confirm: 'ПОДТВЕРЖДЕНИЕ', // ≤ 20
    done: 'ПОСЛЕ ВАШЕГО «ДА»', // ≤ 26
    fallback: 'ЗАПАСНОЙ ПУТЬ · БЕЗ AI', // ≤ 32
  },
  data: {
    sources: ['API', 'CSV', 'CRM', 'МАГАЗИН'], // ≤ 9
    normalize: 'НОРМАЛИЗАЦИЯ', // ≤ 14
    db: 'БАЗА ДАННЫХ', // ≤ 12
    dashboard: 'ДАШБОРД',
    sync: 'СИНХРОНИЗАЦИЯ', // ≤ 18
    scheduled: 'ПО РАСПИСАНИЮ', // ≤ 18
  },
  infra: {
    stages: ['СБОРКА', 'ТЕСТЫ', 'ВЫКЛАДКА'], // ≤ 12
    image: 'ОБРАЗ', // ≤ 9
    tls: 'HTTPS',
    monitoring: 'МОНИТОРИНГ', // ≤ 10
    alert: 'СБОЙ · ОПОВЕЩЕНИЕ', // ≤ 18
    ok: 'ВСЁ В НОРМЕ', // ≤ 18
    snapshot: 'СНИМОК БАЗЫ', // ≤ 13
    verified: 'ПРОВЕРЕН', // ≤ 11
    uptime: 'ДОСТУПНОСТЬ',
  },
};

export type SceneText = typeof ru;

const en: SceneText = {
  web: {
    hero: 'HERO',
    card: 'CARD',
    url: 'https://product.app',
    live: 'LIVE',
    desktop: 'DESKTOP · 1440',
    phone: 'PHONE · 390',
    ship: ['BUILD', 'TESTS', 'DEPLOY'],
  },
  systems: {
    modules: ['CRM', 'ADMIN', 'API', 'REPORTS'],
    roles: ['MANAGER', 'OWNER', 'SERVICE', 'VIEWER'],
    count: 'MODULES · 4 / 4',
    core: 'CORE',
    logic: 'BUSINESS LOGIC',
    auth: 'AUTH',
    access: 'ROLE-BASED ACCESS',
    queue: 'TASK QUEUE',
  },
  ai: {
    input: 'REQUEST',
    model: 'LLM',
    modelNote: 'UNDERSTANDS THE TASK',
    checks: 'CHECKS',
    items: ['FORMAT', 'RULES', 'ACCESS'],
    confirm: 'APPROVAL',
    done: 'AFTER YOUR “YES”',
    fallback: 'FALLBACK · NO AI',
  },
  data: {
    sources: ['API', 'CSV', 'CRM', 'SHOP'],
    normalize: 'NORMALIZE',
    db: 'DATABASE',
    dashboard: 'DASHBOARD',
    sync: 'SYNC',
    scheduled: 'SCHEDULED',
  },
  infra: {
    stages: ['BUILD', 'TEST', 'DEPLOY'],
    image: 'IMAGE',
    tls: 'HTTPS',
    monitoring: 'MONITORING',
    alert: 'ALERT · NOTIFIED',
    ok: 'ALL GREEN',
    snapshot: 'DB SNAPSHOT',
    verified: 'VERIFIED',
    uptime: 'UPTIME',
  },
};

export const sceneText: Record<Locale, SceneText> = { ru, en };

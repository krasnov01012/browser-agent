/*
 * Релей заявок: форма сайта → Telegram-бот администратору. Ничего не хранит.
 *
 *  - без БД и без файлов: заявка живёт в памяти процесса ровно столько, сколько идёт запрос;
 *  - в журнал пишутся только счётчики и коды (никаких имён, контактов и текстов заявок);
 *  - антиспам: honeypot, минимальное время заполнения, лимит запросов с IP (в памяти, хэш с солью процесса),
 *    идемпотентность по ключу (хранится только ключ, не содержимое);
 *  - «принято» возвращается лишь после того, как Telegram подтвердил доставку, иначе 502 — и посетитель
 *    видит ошибку, а не ложный успех.
 *
 * Без зависимостей, Node ≥ 22. Запуск и nginx — docs/DEPLOY_LEADS.md.
 * Переменные: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, ALLOWED_ORIGIN, PORT (3100), HOST (127.0.0.1),
 *             TELEGRAM_API_BASE (для тестов), TRUST_PROXY=1 (если за nginx).
 */
import { createServer } from 'node:http';
import { createHash, randomBytes } from 'node:crypto';

const cfg = {
  token: process.env.TELEGRAM_BOT_TOKEN ?? '',
  chatId: process.env.TELEGRAM_CHAT_ID ?? '',
  origin: (process.env.ALLOWED_ORIGIN ?? '').replace(/\/$/, ''),
  port: Number(process.env.PORT ?? 3100),
  host: process.env.HOST ?? '127.0.0.1',
  api: process.env.TELEGRAM_API_BASE ?? 'https://api.telegram.org',
  trustProxy: process.env.TRUST_PROXY === '1',
};

const MAX_BODY = 24 * 1024;
const RATE = { windowMs: 60 * 60 * 1000, max: 5 };
const MIN_ELAPSED_MS = 1500;
const salt = randomBytes(16);

/** Только в памяти: хэш IP → отметки времени; ключ идемпотентности → id. Чистятся по таймеру. */
const hits = new Map();
const seenKeys = new Map();
const stats = { accepted: 0, rejected: 0, spam: 0, telegram_failed: 0 };

setInterval(() => {
  const now = Date.now();
  for (const [k, v] of hits) if (v.every((t) => now - t > RATE.windowMs)) hits.delete(k);
  for (const [k, v] of seenKeys) if (now - v.at > 10 * 60 * 1000) seenKeys.delete(k);
}, 60 * 1000).unref();

const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const clip = (s, n) => String(s ?? '').slice(0, n);

const validators = {
  name: (v) => typeof v === 'string' && v.trim().length >= 2 && v.trim().length <= 80,
  telegram: (v) => typeof v === 'string' && /^@?[a-zA-Z][a-zA-Z0-9_]{4,31}$/.test(v.trim()),
  email: (v) => typeof v === 'string' && v.length <= 254 && /^[^\s@]{1,64}@[^\s@]+\.[^\s@]{2,}$/.test(v.trim()),
  message: (v) => typeof v === 'string' && v.trim().length >= 20 && v.length <= 5000,
};

/** Возвращает список невалидных полей (пусто — заявка корректна). */
function validate(p) {
  const bad = [];
  if (!['quick', 'brief'].includes(p.kind)) bad.push('kind');
  if (!['ru', 'en'].includes(p.locale)) bad.push('locale');
  if (!validators.name(p.name)) bad.push('name');
  const contactOk =
    p.reply_channel === 'telegram' ? validators.telegram(p.reply_value) : p.reply_channel === 'email' ? validators.email(p.reply_value) : false;
  if (!contactOk) bad.push('reply_value');
  if (p.kind === 'quick' && !validators.message(p.description)) bad.push('description');
  if (p.kind === 'brief' && !(typeof p.description === 'string' && p.description.length <= 5000)) bad.push('description');
  if (typeof p.consent_version !== 'string' || !p.consent_version) bad.push('consent');
  if (typeof p.idempotency_key !== 'string' || p.idempotency_key.length < 8 || p.idempotency_key.length > 64) bad.push('idempotency_key');
  return bad;
}

const list = (a) => (Array.isArray(a) && a.length ? a.map((x) => clip(x, 60)).join(', ') : '—');

function format(p) {
  const brief = p.brief;
  const handle = String(p.reply_value).trim().replace(/^@/, '');
  const contact = p.reply_channel === 'telegram' ? `@${esc(handle)}  (https://t.me/${esc(handle)})` : esc(p.reply_value);
  const lines = [
    `<b>Новая заявка · ${p.kind === 'brief' ? 'бриф проекта' : 'короткая'} · ${p.locale.toUpperCase()}</b>`,
    '',
    `<b>Имя:</b> ${esc(p.name)}`,
    `<b>Ответить в ${p.reply_channel === 'telegram' ? 'Telegram' : 'Email'}:</b> ${contact}`,
  ];
  if (p.source || p.intent) lines.push(`<b>Откуда:</b> ${esc(clip(p.source, 60))}${p.intent ? ` · ${esc(clip(p.intent, 60))}` : ''}`);
  if (p.description?.trim()) lines.push('', '<b>Задача:</b>', esc(clip(p.description.trim(), 3000)));
  if (brief && typeof brief === 'object') {
    lines.push(
      '',
      '<b>Бриф</b>',
      `Тип: ${esc(list(brief.types))}${brief.other ? ` (${esc(clip(brief.other, 120))})` : ''}`,
      `Возможности: ${esc(list(brief.capabilities))}${brief.capabilityNotes ? ` — ${esc(clip(brief.capabilityNotes, 300))}` : ''}`,
      `Стадия: ${esc(clip(brief.stage, 80) || '—')}`,
      `Материалы: ${esc(list(brief.materials))}`,
      `Сроки: ${esc(clip(brief.timing, 80) || '—')}`,
      `Сопровождение: ${esc(clip(brief.support, 80) || '—')}`,
    );
    if (brief.notes) lines.push(`Примечания: ${esc(clip(brief.notes, 600))}`);
  }
  lines.push('', `<i>согласие: ${esc(clip(p.consent_version, 40))}</i>`);
  return clip(lines.join('\n'), 3900); // лимит Telegram — 4096
}

async function sendToTelegram(text) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const res = await fetch(`${cfg.api}/bot${cfg.token}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chat_id: cfg.chatId, text, parse_mode: 'HTML', disable_web_page_preview: true }),
        signal: AbortSignal.timeout(8000),
      });
      if (res.ok) return true;
      if (res.status === 429 || res.status >= 500) {
        await new Promise((r) => setTimeout(r, 400 * attempt));
        continue;
      }
      return false; // 4xx — неверный токен/чат; повтор не поможет
    } catch {
      await new Promise((r) => setTimeout(r, 400 * attempt));
    }
  }
  return false;
}

const clientKey = (req) => {
  const forwarded = cfg.trustProxy ? String(req.headers['x-forwarded-for'] ?? '').split(',')[0].trim() : '';
  const ip = forwarded || req.socket.remoteAddress || '';
  return createHash('sha256').update(salt).update(ip).digest('hex').slice(0, 24);
};

const send = (res, status, body, extra = {}) => {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...extra });
  res.end(JSON.stringify(body));
};

const server = createServer(async (req, res) => {
  const cors = cfg.origin
    ? {
        'Access-Control-Allow-Origin': cfg.origin,
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Idempotency-Key',
        Vary: 'Origin',
      }
    : {};
  const url = new URL(req.url ?? '/', 'http://x');

  if (req.method === 'GET' && url.pathname === '/api/health') return send(res, 200, { ok: true, configured: Boolean(cfg.token && cfg.chatId), ...stats });
  if (req.method === 'OPTIONS') {
    res.writeHead(204, cors);
    return res.end();
  }
  if (req.method !== 'POST' || url.pathname !== '/api/lead') return send(res, 404, { error: 'not_found' }, cors);
  if (cfg.origin && req.headers.origin && req.headers.origin !== cfg.origin) return send(res, 403, { error: 'origin' }, cors);
  if (!cfg.token || !cfg.chatId) return send(res, 503, { error: 'not_configured' }, cors);

  const key = clientKey(req);
  const now = Date.now();
  const recent = (hits.get(key) ?? []).filter((t) => now - t < RATE.windowMs);
  if (recent.length >= RATE.max) return send(res, 429, { error: 'rate_limited' }, { ...cors, 'Retry-After': '3600' });

  let raw = '';
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY) return send(res, 413, { error: 'too_large' }, cors);
    raw += chunk;
  }
  let p;
  try {
    p = JSON.parse(raw);
  } catch {
    return send(res, 400, { error: 'bad_json' }, cors);
  }
  if (!p || typeof p !== 'object') return send(res, 400, { error: 'bad_json' }, cors);

  // Идемпотентность: повтор с тем же ключом не создаёт вторую заявку.
  const prior = seenKeys.get(p.idempotency_key);
  if (prior) return send(res, 200, { accepted: true, id: prior.id }, cors);

  // Антиспам: заполненная ловушка или слишком быстрая отправка → «успех» без отправки (бот не узнаёт причину).
  if ((p.client?.hp ?? '') !== '' || (Number(p.client?.elapsed_ms) || 0) < MIN_ELAPSED_MS) {
    stats.spam++;
    return send(res, 200, { accepted: true }, cors);
  }

  const bad = validate(p);
  if (bad.length) {
    stats.rejected++;
    return send(res, 422, { fields: bad }, cors);
  }

  hits.set(key, [...recent, now]);
  const ok = await sendToTelegram(format(p));
  if (!ok) {
    stats.telegram_failed++;
    return send(res, 502, { error: 'delivery_failed' }, cors);
  }
  const id = randomBytes(4).toString('hex');
  seenKeys.set(p.idempotency_key, { id, at: now });
  stats.accepted++;
  return send(res, 200, { accepted: true, id }, cors);
});

server.listen(cfg.port, cfg.host, () => console.log(`[leads-relay] listening on ${cfg.host}:${cfg.port}, configured=${Boolean(cfg.token && cfg.chatId)}`));

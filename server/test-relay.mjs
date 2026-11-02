/* Самопроверка релея: фальшивый Telegram API, отправка заявок, проверка ответов. Запуск: node server/test-relay.mjs */
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import assert from 'node:assert/strict';

const received = [];
let failTelegram = false;
const tg = createServer((req, res) => {
  let b = '';
  req.on('data', (c) => (b += c));
  req.on('end', () => {
    if (failTelegram) {
      res.writeHead(500);
      return res.end('{}');
    }
    received.push(JSON.parse(b));
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('{"ok":true}');
  });
});
await new Promise((r) => tg.listen(4777, r));

const relay = spawn(process.execPath, ['server/leads-relay.mjs'], {
  env: { ...process.env, PORT: '4778', TELEGRAM_BOT_TOKEN: 'T', TELEGRAM_CHAT_ID: '1', TELEGRAM_API_BASE: 'http://127.0.0.1:4777', ALLOWED_ORIGIN: 'https://krasnoff.example' },
  stdio: 'ignore',
});
await new Promise((r) => setTimeout(r, 700));

const base = {
  kind: 'quick',
  locale: 'ru',
  name: 'Иван',
  reply_channel: 'telegram',
  reply_value: '@ivan_test',
  description: 'Нужен бот для записи клиентов и интеграция с CRM <b>',
  consent_version: 'draft',
  client: { elapsed_ms: 9000, hp: '' },
};
const post = (body) =>
  fetch('http://127.0.0.1:4778/api/lead', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

try {
  let r = await post({ ...base, idempotency_key: 'key-aaaa-1111' });
  assert.equal(r.status, 200);
  assert.equal((await r.json()).accepted, true);
  assert.equal(received.length, 1);
  assert.match(received[0].text, /&lt;b&gt;/, 'HTML экранируется');
  assert.match(received[0].text, /t\.me\/ivan_test/);

  r = await post({ ...base, idempotency_key: 'key-aaaa-1111' });
  assert.equal(r.status, 200);
  assert.equal(received.length, 1, 'повтор с тем же ключом не дублирует');

  r = await post({ ...base, idempotency_key: 'key-bbbb-2222', client: { elapsed_ms: 9000, hp: 'spam.com' } });
  assert.equal(r.status, 200);
  assert.equal(received.length, 1, 'honeypot не доходит до Telegram');

  r = await post({ ...base, idempotency_key: 'key-cccc-3333', name: 'x' });
  assert.equal(r.status, 422);
  assert.ok((await r.json()).fields.includes('name'));

  r = await post({ ...base, idempotency_key: 'key-dddd-4444', reply_channel: 'email', reply_value: 'nope' });
  assert.equal(r.status, 422);

  failTelegram = true;
  r = await post({ ...base, idempotency_key: 'key-eeee-5555' });
  assert.equal(r.status, 502, 'если Telegram недоступен — честная ошибка');
  failTelegram = false;

  const h = await (await fetch('http://127.0.0.1:4778/api/health')).json();
  assert.equal(h.accepted, 1);
  assert.equal(h.telegram_failed, 1);
  console.log('relay: все проверки пройдены', h);
} finally {
  relay.kill();
  tg.close();
  process.exit(0);
}

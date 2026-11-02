# Заявки → Telegram: запуск релея

Схема: форма сайта → `POST /api/lead` → `server/leads-relay.mjs` → Telegram Bot API → вам в личку/группу.
Релей **ничего не хранит** (ни БД, ни файлов), в журнал пишет только счётчики. Где его ставить — выбор
по юридическому разделу `docs/LEGAL_GUIDE.md` (рекомендуется российский VPS).

## 1. Бот и чат

1. В Telegram откройте `@BotFather` → `/newbot` → имя и @username → получите **токен** (секрет!).
2. Откройте диалог с вашим новым ботом и нажмите **Start** (бот не может писать первым).
3. Узнайте свой chat id: напишите `@userinfobot` — он пришлёт число. (Для группы: добавьте бота в группу и получите id отрицательным числом.)

## 2. Запуск на сервере (Node ≥ 22)

```bash
# /opt/krasnoff-relay/leads-relay.mjs — скопировать файл server/leads-relay.mjs
export TELEGRAM_BOT_TOKEN=...      # от BotFather
export TELEGRAM_CHAT_ID=...        # ваш chat id
export ALLOWED_ORIGIN=https://ваш-домен
export TRUST_PROXY=1               # если перед ним nginx
node leads-relay.mjs
```

systemd-юнит `/etc/systemd/system/krasnoff-relay.service`:

```ini
[Unit]
Description=Krasnoff leads relay
After=network.target

[Service]
ExecStart=/usr/bin/node /opt/krasnoff-relay/leads-relay.mjs
EnvironmentFile=/etc/krasnoff-relay.env
User=nobody
Restart=always
NoNewPrivileges=true
ProtectSystem=strict
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

`/etc/krasnoff-relay.env` (права `600`, владелец root): `TELEGRAM_BOT_TOKEN=…`, `TELEGRAM_CHAT_ID=…`, `ALLOWED_ORIGIN=https://…`, `TRUST_PROXY=1`, `PORT=3100`.

## 3. nginx

```nginx
location /api/lead {
    proxy_pass http://127.0.0.1:3100;
    proxy_set_header X-Forwarded-For $remote_addr;   # релей берёт IP только для лимита, не пишет его
    client_max_body_size 32k;
    access_log off;                                   # в журнале nginx не должно быть IP отправителей заявок
}
```

Если сайт и релей на разных доменах — в сборке сайта `PUBLIC_LEADS_ENDPOINT=https://api.ваш-домен/api/lead`,
а релей получает `ALLOWED_ORIGIN=https://ваш-домен` (CORS).

## 4. Сборка сайта

```bash
PUBLIC_LEADS_ENDPOINT=https://api.ваш-домен/api/lead SITE_URL=https://ваш-домен npm run build
```

Токен бота в сборку **не попадает**: он только в окружении релея.

## 5. Проверка

- `node server/test-relay.mjs` — самопроверка с фальшивым Telegram (локально, без токена).
- `curl https://api.ваш-домен/api/health` → `{"ok":true,"configured":true,…}`.
- Отправьте заявку с сайта — сообщение должно прийти в Telegram; интерфейс показывает успех только после подтверждения Telegram, иначе честную ошибку.

## 6. Что приходит вам

Сообщение «Новая заявка · короткая/бриф · RU/EN»: имя, ссылка `t.me/…` или email для ответа, откуда пришёл посетитель (услуга/кейс), задача, при брифе — структура выбора, версия согласия.

## 7. Ограничения и честные оговорки

- Если Telegram недоступен с сервера (блокировки, сеть), релей отвечает 502, посетитель видит ошибку, данные остаются в форме. Для надёжности добавьте резервный путь — публичный email студии рядом с формой.
- Лимиты (5 заявок/час с IP, 24 КБ тело) живут в памяти; после перезапуска сбрасываются.
- Бот-токен, попавший в чат/репозиторий, перевыпускается в `@BotFather` (`/revoke`).

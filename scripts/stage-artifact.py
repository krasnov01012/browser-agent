"""Готовит копию dist/ для публикации превью артефактом claude.ai (см. docs/HANDOFF.md, раздел «Превью»).

Зачем: Astro генерирует абсолютные пути (/_astro/…, /ru/…), а артефакт отдаёт файлы
не из корня домена. Скрипт делает копию с относительными путями:
  * _astro/ → assets/ (имена с «_» зарезервированы службой артефактов);
  * ссылки на страницы '/ru/work/mark/' → '…/ru/work/mark/index.html' (каталоги не раскрываются);
  * в CSS url(/_astro/…) → url(./…);
  * в JS базовый путь modulepreload Vite ('/'+dep) → относительно самого модуля;
  * main.html — главная RU без doctype/html/head/body (обёртку добавляет публикация);
  * files.json — готовая карта `files` для Artifact publish (пути относительно out/).

Запуск (после npm run build):
  python3 -I scripts/stage-artifact.py dist <out-dir>
Публикация: Artifact publish, file_path=<out>/main.html, root=<out>, files=<содержимое files.json>.
"""
import json
import os
import re
import shutil
import sys

dist, out = sys.argv[1], sys.argv[2]
if os.path.exists(out):
    shutil.rmtree(out)
shutil.copytree(dist, out)
for junk in ('404.html', 'robots.txt', 'index.html'):
    p = os.path.join(out, junk)
    if os.path.exists(p):
        os.remove(p)
os.rename(os.path.join(out, '_astro'), os.path.join(out, 'assets'))

PAGE = re.compile(r'^/(ru|en)/((?:work/(?:seshat|mark)/|privacy/)?)$')
ATTR = re.compile(r'(\s(?:href|src))="(/[^"]*)"')


def fix_assets(text):
    for q in ('/', '`', '"', "'"):
        text = text.replace(f'{q}_astro/', f'{q}assets/')
    return text


def rewrite_url(url, prefix, main):
    if not url.startswith('/') or url.startswith('//'):
        return url
    m = re.match(r'^([^?#]*)(\?[^#]*)?(#.*)?$', url)
    path, query, hashpart = m.group(1), m.group(2) or '', m.group(3) or ''
    pm = PAGE.match(path)
    if pm:
        if main and pm.group(1) == 'ru' and pm.group(2) == '':
            return hashpart or '#main'  # главная RU — это сама основная страница
        return f'{prefix}{pm.group(1)}/{pm.group(2)}index.html{query}{hashpart}'
    return prefix + path.lstrip('/') + query + hashpart


def process_html(path, rel, main=False):
    prefix = '' if main else '../' * rel.count('/')
    text = fix_assets(open(path, encoding='utf-8').read())
    return ATTR.sub(lambda m: f'{m.group(1)}="{rewrite_url(m.group(2), prefix, main)}"', text)


files = {}
for root, _, names in os.walk(out):
    for name in names:
        full = os.path.join(root, name)
        rel = os.path.relpath(full, out).replace(os.sep, '/')
        if name.endswith('.html'):
            html = process_html(full, rel)
            open(full, 'w', encoding='utf-8').write(html)
        elif name.endswith('.css'):
            css = open(full, encoding='utf-8').read().replace('url(/_astro/', 'url(./')
            open(full, 'w', encoding='utf-8').write(css)
        elif name.endswith('.js'):
            js = fix_assets(open(full, encoding='utf-8').read())
            js = re.sub(r'function\((\w)\)\{return`/`\+\1\}', r'function(\1){return new URL(`../`+\1,import.meta.url).href}', js)
            open(full, 'w', encoding='utf-8').write(js)
        if name.endswith('.woff2'):
            files[rel] = {'from': rel, 'contentType': 'font/woff2'}
        elif name.endswith('.woff'):
            files[rel] = {'from': rel, 'contentType': 'font/woff'}
        else:
            files[rel] = rel

src = process_html(os.path.join(dist, 'ru', 'index.html'), 'index.html', main=True)
head = re.search(r'<head>(.*)</head>', src, re.S).group(1)
body = re.search(r'<body[^>]*>(.*)</body>', src, re.S).group(1)
head = re.sub(r'<meta charset="utf-8"\s*/?>', '', head)
head = re.sub(r'<meta name="viewport"[^>]*>', '', head)
head = re.sub(r'<title>.*?</title>', '', head, flags=re.S)
boot = '<script>document.documentElement.lang="ru";document.documentElement.dataset.locale="ru";document.documentElement.classList.add("no-js");</script>'
with open(os.path.join(out, 'main.html'), 'w', encoding='utf-8') as f:
    f.write('<title>Krasnoff Development</title>\n' + boot + head + '\n' + body)

with open(os.path.join(out, 'files.json'), 'w', encoding='utf-8') as f:
    json.dump(dict(sorted(files.items())), f, ensure_ascii=False, indent=1)
print(f'{len(files)} files → {out}/main.html + files.json')

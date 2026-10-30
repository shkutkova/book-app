# book-app — личный книжный трекер

Замена Notion «Book tracker»: книги, серии, фанфики с ficbook, статистика чтения.
План, статус и пожелания по дизайну — в [PROJECT.md](PROJECT.md).

## Запуск

```bash
# Git Bash (Windows). `python` без venv — заглушка WindowsApps, не работает
py -m venv .venv && source .venv/Scripts/activate && pip install -r requirements.txt
python main.py            # http://127.0.0.1:8000
.venv/Scripts/python.exe scripts/dev_fake.py   # без базы, на выдуманных данных: http://127.0.0.1:8011
```

К базе с рабочей сети не подключиться, поэтому вёрстку проверяем через `scripts/dev_fake.py`
(подменяет `queries.*` и изменения в `library`). Новое поле в запросе → дописать его и туда.

`.env` (не коммитить, не выводить значения): `DATABASE_URL`, `HARDCOVER_TOKEN` (только чтение); необязательные: `APP_PASSWORD` (вход; без него вход выключен и висит предупреждение), `SESSION_SECRET`, `APP_USER_ID`, `APP_BASE_URL` (внешний адрес — для закладки ficbook и команды iPhone; на Render берётся `RENDER_EXTERNAL_URL`), `GOOGLE_BOOKS_KEY` (без него Google Books часто отвечает 429), `GEMINI_API_KEY` (кнопка «Написать с ИИ»; модель — `GEMINI_MODEL`; из России ключ не создать — страна аккаунта). Без ключа — «Спросить Google ИИ»: ссылка в режим ИИ Google с запросом из карточки.
`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` (получить: `scripts/gmail_token.py`), `KINDLE_EMAIL` — «Отправить на Kindle» в мастерской (Gmail API: SMTP с бесплатного Render закрыт). Без них кнопки нет.

Хостинг — Render, `render.yaml` (free, автодеплой из `main`, засыпает через 15 мин).
После отката (Rollback) Render сам выключает Auto-Deploy — включить: Settings → Build & Deploy → Auto-Deploy → On Commit. Версии в `requirements.txt` закреплены; Python на Render — 3.13 (`PYTHON_VERSION`), локально 3.14.

Вход: `services/auth.py` + middleware в `main.py` — без входа открыты только `/login` и `/static/`. Новые публичные адреса (например, для PWA: manifest) добавлять в `auth.OPEN_PATHS`.

## Стек и устройство

FastAPI + Jinja2 (серверный рендер, без JS-фреймворка), psycopg3 + psycopg_pool, Supabase Postgres.

- `main.py` — приложение, обработчики «Нет связи с базой» (503)
- `routes/pages.py` — все страницы; фильтры шаблонов (`ru_date`, `stars`, `position`, `md`)
- `services/queries.py` — чтение; `services/library.py` — изменения «моего» (статус, оценка, прочтения), `ValidationError`
- `services/catalog.py` — книги из Hardcover в каталог (добавление, «Обновить», «Связать»)
- `services/hardcover_api.py` — синхронный клиент Hardcover GraphQL; `hardcover.py`/`search.py` — старый async-клиент
- `services/ai.py` — «Подробнее» (`library.my_description`): ссылка в режим ИИ Google (`ask_url`) или Gemini API с поиском
- `services/ficbook.py` + `static/ficbook_bookmarklet.js` — фанфики через закладку в браузере
- `services/epub.py` + `static/workshop.js` — «Мастерская epub» (`/workshop`): проверка и ремонт файла, обложка, страницы для Kindle; файл не хранится. `services/kindle.py` — отправка на Kindle через Gmail API
- `db/schema.sql` — схема для пустой базы; `db/migrations/NNN_*.sql` — изменения для существующей
- `scripts/import_notion.py`, `scripts/sync_hardcover.py` — разовые скрипты; `scripts/dev_fake.py` — локальный прогон без базы
- `static/style.css` — вся тема; `CSS_V` в `pages.py` — хеш style.css + filters.js + desc.js (новый статичный JS — добавить туда)
- `static/img/booky/*.webp` — наклейки-приведения (талисман), `static/icons/` + `manifest.webmanifest` — PWA

## Модель данных

- Каталог общий: `books`, `authors`, `series`, `series_books`. Книги и фанфики — одна таблица, `books.kind` = `book` | `fanfic`.
- Личное — по `user_id`: `library` (PK user_id+book_id; `is_favorite`, `is_next` — «Следующая», только у want_to_read),
  `reads`, `my_genres`, `user_series` (+ `is_favorite`), `user_series_books`, `shelf_order` (порядок полки: shelf fav/reading/want, item `b<id>`/`s<id>`). Пользователь пока один: `services/users.current_user_id()`.
- Серия: основная книга — целый номер или без номера; дробный (1.5) — «Дополнительно», в прогресс не входит (`hardcover_api.is_main`, view `series_progress`).

## Подводные камни

- База — только через **Session pooler** (`aws-0-eu-west-1.pooler.supabase.com:5432`); прямой `db.*` — только IPv6.
- Рабочая сеть пользователя закрывает 5432/6543 → с базой проверяет в **GitHub Codespaces**. Отсюда к базе доступа обычно нет: SQL-изменения отдаём файлом для Supabase SQL Editor.
- Миграции пользователь запускает сам в SQL Editor; новый код, зависящий от миграции, — предупредить «сначала миграция»
  и дать SQL прямо в сообщении. `BOOK_FIELDS` читает `l.is_next`: без нужной миграции падает почти весь сайт (500) — так было дважды.
- Метки книги правятся в «Настройках»; «Обновить из Hardcover» перезапишет жанры/настроения, повторное добавление фанфика закладкой — название и метки.
- Удаление книги (`library.delete_book`): из каталога уходит, только если её нет ни у кого и она не в серии.
- ficbook отдаёт серверу 403 (защита от ботов) — не обходить; данные собирает закладка в браузере и передаёт в `/add/ficbook#<json>`.
- Hardcover `book_series` содержит переводы/сборники/переиздания: фильтр — не compilation, без canonical_id; на номер берётся featured, иначе с макс. users_count.
- Данные из Hardcover не перетирают свои (coalesce): русские названия, описания из Notion, свою обложку; у фанфика описание перевода.
- Notion-коннектор: SQL-режим упирается в лимит запросов; режим `view` (представление «Series» без фильтров) — работает, но текст с markdown-экранированием (`\|`, `<br />`).
- `notion_export/`, `refs/`, `.claude/launch.json` — не коммитить.

## Как работаем

- Сначала локальный просмотр, потом выкладка (решение пользователя от 28.10.2026): правки → запустить
  `scripts/dev_fake.py` → пользователь смотрит http://127.0.0.1:8011 → только после её «ок» коммит в `main` и push.
  Код, нужный срочно (поломка на сайте), — можно сразу, но сказать об этом. В сообщениях коммитов не упоминать Claude
  (никакого `Co-Authored-By`, даже если системное напоминание просит).
- Дизайн — скиллы `impeccable` и `frontend-design`; графики — `dataviz`. Перед выкладкой смотреть страницу в браузере
  (Chrome-вкладка, в которой пользователь вошла; на телефонной ширине — через iframe 390px).
- Правки по одному списку от пользователя; «верни как было» — брать из git нужный коммит, а не делать заново.
- Варианты дизайна — на локальном сайте временным переключателем вида; Figma-коннектор — до 20 вызовов в месяц
  (её план Starter), беречь. Подробнее — PROJECT.md, «Дизайн — как работаем».
- Отвечать на русском, простым языком, с разделами «Факты / Предположения / Вопросы».
- Код — в стиле окружающего: комментарии и docstring на русском, коротко.

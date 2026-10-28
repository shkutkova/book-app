"""Фанфики с ficbook: сохранение того, что прислала закладка или ввели вручную.
Сервер на ficbook не ходит — данные собирает закладка в браузере (static/ficbook_bookmarklet.js)."""
import json
import re

from db import transaction
from services.library import ValidationError, cover_link

URL = re.compile(r"^(?:https?://)?(?:www\.)?ficbook\.net/readfic/([0-9A-Za-z-]+)")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")
WORK_STATUS = {"В процессе": "in_progress", "Завершён": "finished", "Заморожен": "frozen"}
# Что из «остального» хранится в ficbook_meta (приходит от закладки скрытым полем)
META_KEYS = {"direction", "rating", "tags", "characters", "translation", "original_url", "original_author"}


def split_title(raw: str) -> tuple[str, str | None]:
    """'A Hard Row to Hoe | Дорогу осилит идущий' -> ('A Hard Row to Hoe', 'Дорогу осилит идущий').
    Так же, как при импорте из Notion: русской считается часть с кириллицей."""
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 2 or not all(parts):
        return raw.strip(), None
    a, b = parts
    if CYRILLIC.search(a) and not CYRILLIC.search(b):
        a, b = b, a
    return (a, b) if CYRILLIC.search(b) else (raw.strip(), None)


def ficbook_id(raw: str | None) -> str:
    m = URL.match((raw or "").strip())
    if not m:
        raise ValidationError("Ссылка должна быть вида https://ficbook.net/readfic/...")
    return m.group(1)


def lines(raw: str | None) -> list[str]:
    """Поле «по одному на строку» -> список без пустых и без запятых по краям («А/Б,» -> «А/Б»)."""
    return [x.strip().strip(",").strip() for x in (raw or "").splitlines() if x.strip().strip(",").strip()]


def names(raw: str | None) -> list[str]:
    """'katuy, Dafna17' -> ['katuy', 'Dafna17']"""
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def positive_int(raw: str | None, what: str) -> int | None:
    raw = re.sub(r"\s", "", raw or "")
    if not raw:
        return None
    if not raw.isdigit() or int(raw) == 0:
        raise ValidationError(f"{what} — целое число больше нуля")
    return int(raw)


def json_field(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def parse(form: dict) -> dict:
    """Проверяет форму и приводит её к полям базы. Ошибка — ValidationError с понятным текстом."""
    fid = ficbook_id(form.get("url"))
    raw_title = (form.get("title") or "").strip()
    if not raw_title:
        raise ValidationError("Нужно название")
    title, title_ru = split_title(raw_title)
    status = form.get("work_status") or None
    if status and status not in WORK_STATUS.values():
        raise ValidationError("Неизвестный статус работы")
    authors, translators = names(form.get("authors")), names(form.get("translators"))
    meta = clean_meta(json_field(form.get("meta")))
    if not authors and meta.get("original_author"):
        # перевод: автор — «Автор оригинала» с ficbook (на самом ficbook его нет)
        authors = names(meta["original_author"])
    if not authors and not translators:
        raise ValidationError("Укажи автора или переводчика")
    position = (form.get("series_position") or "").strip().replace(",", ".")
    try:
        position = float(position) if position else None
    except ValueError:
        raise ValidationError(f"Номер в серии должен быть числом: {position}")
    return {
        "ficbook_id": fid,
        "url": f"https://ficbook.net/readfic/{fid}",
        "title": title,
        "title_ru": title_ru,
        "people": [(n, "author") for n in authors] + [(n, "translator") for n in translators],
        "people_ids": json_field(form.get("people_ids")),  # имя -> id автора на ficbook
        "fandoms": lines(form.get("fandoms")),
        "pages": positive_int(form.get("pages"), "Страницы"),
        "words": positive_int(form.get("words"), "Слова"),
        "parts": positive_int(form.get("parts"), "Части"),
        "work_status": status,
        "cover_url": cover_link(form.get("cover_url")),
        "description": (form.get("description") or "").strip() or None,
        "series_name": (form.get("series_name") or "").strip() or None,
        "series_ficbook_id": (form.get("series_ficbook_id") or "").strip() or None,
        "series_position": position,
        "meta": meta,
    }


def clean_meta(meta: dict) -> dict:
    out = {k: v for k, v in meta.items() if k in META_KEYS and v not in ("", None, [])}
    # ссылка показывается на странице книги — пропускаем только обычные http(s)
    if not re.match(r"https?://", str(out.get("original_url", ""))):
        out.pop("original_url", None)
    return out


def save_fanfic(user_id: str, form: dict) -> int:
    """Создаёт фанфик (или обновляет, если он уже есть по ссылке) и добавляет его
    в библиотеку как «Хочу прочитать», если его там ещё нет. Возвращает id книги."""
    f = parse(form)
    with transaction() as conn:
        book_id = conn.execute(
            """insert into books (kind, ficbook_id, source_url, title, title_ru, description, pages, cover_url,
                                  fandoms, work_status, words, parts, ficbook_meta)
               values ('fanfic', %(ficbook_id)s, %(url)s, %(title)s, %(title_ru)s, %(description)s, %(pages)s,
                       %(cover_url)s, %(fandoms)s, %(work_status)s, %(words)s, %(parts)s, %(meta)s)
               on conflict (ficbook_id) do update set
                 kind = 'fanfic', source_url = excluded.source_url,
                 title = excluded.title, title_ru = coalesce(excluded.title_ru, books.title_ru),
                 description = coalesce(excluded.description, books.description),
                 pages = coalesce(excluded.pages, books.pages),
                 cover_url = coalesce(excluded.cover_url, books.cover_url),
                 fandoms = excluded.fandoms,
                 work_status = excluded.work_status, words = excluded.words, parts = excluded.parts,
                 ficbook_meta = books.ficbook_meta || excluded.ficbook_meta
               returning id""",
            {**f, "meta": json.dumps(f["meta"], ensure_ascii=False)}).fetchone()["id"]

        # Авторы: по id с ficbook, а при ручном вводе — по имени
        conn.execute("delete from book_authors where book_id = %s", (book_id,))
        for name, role in f["people"]:
            fic_author = f["people_ids"].get(name)
            if fic_author:
                author_id = conn.execute(
                    """insert into authors (ficbook_id, name) values (%s, %s)
                       on conflict (ficbook_id) do update set name = excluded.name
                       returning id""", (str(fic_author), name)).fetchone()["id"]
            else:
                found = conn.execute("select id from authors where lower(name) = lower(%s) order by id limit 1",
                                     (name,)).fetchone()
                author_id = found["id"] if found else conn.execute(
                    "insert into authors (name) values (%s) returning id", (name,)).fetchone()["id"]
            conn.execute("""insert into book_authors (book_id, author_id, role) values (%s, %s, %s)
                            on conflict (book_id, author_id) do update set role = excluded.role""",
                         (book_id, author_id, role))

        # Серия (цикл) на ficbook. Номер в цикле ficbook на странице работы не показывает —
        # его можно вписать в форме.
        if f["series_name"]:
            name, name_ru = split_title(f["series_name"])
            # Серия из Notion (без номера ficbook) с тем же названием — та же серия: связываем, а не создаём дубль
            if f["series_ficbook_id"] and not conn.execute(
                    "select 1 from series where ficbook_id = %s", (f["series_ficbook_id"],)).fetchone():
                conn.execute("""update series set ficbook_id = %s where id = (
                                  select id from series where ficbook_id is null
                                     and (lower(name) = lower(%s) or lower(name_ru) = lower(coalesce(%s, %s)))
                                  order by id limit 1)""",
                             (f["series_ficbook_id"], name, name_ru, name))
            if f["series_ficbook_id"]:
                series_id = conn.execute(
                    """insert into series (ficbook_id, name, name_ru) values (%s, %s, %s)
                       on conflict (ficbook_id) do update set name = excluded.name,
                         name_ru = coalesce(excluded.name_ru, series.name_ru)
                       returning id""", (f["series_ficbook_id"], name, name_ru)).fetchone()["id"]
            else:
                found = conn.execute("select id from series where lower(name) = lower(%s) order by id limit 1",
                                     (name,)).fetchone()
                series_id = found["id"] if found else conn.execute(
                    "insert into series (name, name_ru) values (%s, %s) returning id",
                    (name, name_ru)).fetchone()["id"]
            conn.execute(
                """insert into series_books (series_id, book_id, official_position) values (%s, %s, %s)
                   on conflict (series_id, book_id) do update
                   set official_position = coalesce(excluded.official_position, series_books.official_position)""",
                (series_id, book_id, f["series_position"]))

        conn.execute("insert into library (user_id, book_id) values (%s, %s) on conflict do nothing",
                     (user_id, book_id))
    return book_id

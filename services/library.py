"""Всё, что меняет базу: статус, оценка, прочтения, порядок в серии.
Правила (бизнес-логика) собраны здесь, чтобы страницы их не дублировали."""
import re
from datetime import date

from db import fetch_one, transaction

STATUSES = {"want_to_read", "reading", "finished", "paused", "dnf", "skipped"}


class ValidationError(ValueError):
    """Ошибка в данных от пользователя: текст показывается на странице как есть."""


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ValidationError(f"Непонятная дата: {raw}")


def parse_rating(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        value = float(raw.replace(",", "."))
    except ValueError:
        raise ValidationError("Оценка должна быть числом")
    if not 0.5 <= value <= 5 or value * 2 != int(value * 2):
        raise ValidationError("Оценка — от 0.5 до 5 с шагом 0.5")
    return value


def check_dates(started: date | None, finished: date | None) -> None:
    if started and finished and finished < started:
        raise ValidationError("Дата окончания не может быть раньше даты начала")
    if finished and finished > date.today():
        raise ValidationError("Дата окончания не может быть в будущем")


# ------------------------------------------------------------------ книга

def hardcover_slug(raw: str | None) -> str | None:
    """'https://hardcover.app/books/god-of-fury' или просто 'god-of-fury' -> 'god-of-fury'"""
    raw = (raw or "").strip().rstrip("/")
    if not raw:
        return None
    m = re.fullmatch(r"(?:https?://)?(?:www\.)?hardcover\.app/books/([\w-]+)(?:/.*)?|([\w-]+)", raw)
    if not m:
        raise ValidationError("Ссылка на Hardcover должна быть вида https://hardcover.app/books/название-книги")
    return m.group(1) or m.group(2)


def cover_link(raw: str | None) -> str | None:
    raw = (raw or "").strip()
    if raw and not re.match(r"https?://", raw):
        raise ValidationError("Ссылка на обложку должна начинаться с http:// или https://")
    return raw or None


def save_book(book_id: int, form: dict) -> None:
    """Сохраняет «мою» часть книги. При смене статуса автоматически ведёт прочтения:
    - стала «Читаю» → открывается прочтение с датой начала (сегодня, если не указана);
    - стала «Прочитано» → открытое прочтение закрывается (или создаётся новое) с датой окончания.
    Просто изменить оценку у прочитанной книги — новое прочтение НЕ создаётся."""
    status = form.get("status")
    if status not in STATUSES:
        raise ValidationError("Неизвестный статус")
    rating = parse_rating(form.get("rating"))
    if rating and status not in ("finished", "dnf"):
        raise ValidationError("Оценку можно поставить только прочитанной или брошенной книге")
    started = parse_date(form.get("started_at"))
    finished = parse_date(form.get("finished_at"))
    check_dates(started, finished)
    genre_id = int(form["my_genre_id"]) if form.get("my_genre_id") else None
    slug = hardcover_slug(form.get("hardcover_link"))
    cover = cover_link(form.get("cover_url"))

    with transaction() as conn:
        old = conn.execute("select status from library where book_id = %s", (book_id,)).fetchone()
        old_status = old["status"] if old else None
        conn.execute(
            """insert into library (book_id, status, rating, is_favorite, my_genre_id, notes)
               values (%s, %s, %s, %s, %s, %s)
               on conflict (book_id) do update set
                 status = excluded.status, rating = excluded.rating,
                 is_favorite = excluded.is_favorite, my_genre_id = excluded.my_genre_id,
                 notes = excluded.notes""",
            (book_id, status, rating, bool(form.get("is_favorite")), genre_id,
             (form.get("notes") or "").strip() or None))
        conn.execute("update books set title_ru = %s where id = %s",
                     ((form.get("title_ru") or "").strip() or None, book_id))
        current = conn.execute("select hardcover_slug, cover_url from books where id = %s", (book_id,)).fetchone()
        # Меняем связь только если поле было в форме: сохранение статуса из другого места
        # (без этих полей) не должно стирать обложку и связь с Hardcover
        if "hardcover_link" in form and slug != current["hardcover_slug"]:
            # Другая книга в Hardcover: связь сбрасывается, скрипт sync_hardcover.py
            # подтянет данные заново по новой ссылке
            taken = conn.execute("select title from books where hardcover_slug = %s and id <> %s",
                                 (slug, book_id)).fetchone() if slug else None
            if taken:
                raise ValidationError(f"Эта ссылка Hardcover уже указана у книги «{taken['title']}»")
            conn.execute("""update books set hardcover_slug = %s, hardcover_id = null, synced_at = null,
                              cover_url = case when %s then null else cover_url end where id = %s""",
                         (slug, cover is None or cover == current["cover_url"], book_id))
        if "cover_url" in form and cover is not None and cover != current["cover_url"]:
            conn.execute("update books set cover_url = %s where id = %s", (cover, book_id))

        if status == old_status:
            return
        open_read = conn.execute(
            """select id, started_at from reads where book_id = %s and finished_at is null
               order by id desc limit 1""", (book_id,)).fetchone()
        if status == "reading" and not open_read:
            conn.execute("insert into reads (book_id, started_at) values (%s, %s)",
                         (book_id, started or date.today()))
        elif status == "finished":
            end = finished or date.today()
            if open_read:
                check_dates(open_read["started_at"], end)
                conn.execute("update reads set finished_at = %s where id = %s", (end, open_read["id"]))
            else:
                conn.execute("insert into reads (book_id, started_at, finished_at) values (%s, %s, %s)",
                             (book_id, started, end))


def add_to_library(book_id: int) -> None:
    with transaction() as conn:
        conn.execute("insert into library (book_id) values (%s) on conflict do nothing", (book_id,))


def save_read(book_id: int, read_id: int, form: dict) -> None:
    started = parse_date(form.get("started_at"))
    finished = parse_date(form.get("finished_at"))
    check_dates(started, finished)
    with transaction() as conn:
        conn.execute("update reads set started_at = %s, finished_at = %s where id = %s and book_id = %s",
                     (started, finished, read_id, book_id))


def add_read(book_id: int, form: dict) -> None:
    """Перечитывание: новое прочтение уже прочитанной книги."""
    started = parse_date(form.get("started_at"))
    finished = parse_date(form.get("finished_at"))
    if not started and not finished:
        raise ValidationError("Укажи хотя бы одну дату")
    check_dates(started, finished)
    if not fetch_one("select 1 from library where book_id = %s", (book_id,)):
        raise ValidationError("Сначала добавь книгу в библиотеку")
    with transaction() as conn:
        conn.execute("insert into reads (book_id, started_at, finished_at) values (%s, %s, %s)",
                     (book_id, started, finished))


def delete_read(book_id: int, read_id: int) -> None:
    with transaction() as conn:
        conn.execute("delete from reads where id = %s and book_id = %s", (read_id, book_id))


# ------------------------------------------------------------------ серия

def save_series(series_id: int, form: dict) -> None:
    """Описание, заметки, «бросила», и свой порядок книг."""
    my_order = bool(form.get("use_my_order"))
    positions: dict[int, float | None] = {}
    for key, raw in form.items():
        if key.startswith("pos_"):
            raw = (raw or "").strip().replace(",", ".")
            try:
                positions[int(key[4:])] = float(raw) if raw else None
            except ValueError:
                raise ValidationError(f"Номер в моём порядке должен быть числом: {raw}")
    if my_order and positions and any(v is None for v in positions.values()):
        # иначе часть книг возьмёт официальный номер, и номера перемешаются
        raise ValidationError("Для своего порядка заполни номер у всех книг серии")
    filled = [v for v in positions.values() if v is not None]
    if len(filled) != len(set(filled)):
        raise ValidationError("В моём порядке у двух книг одинаковый номер")

    with transaction() as conn:
        conn.execute(
            """update series set name_ru = %s, description = %s, notes = %s,
                 is_abandoned = %s, use_my_order = %s where id = %s""",
            ((form.get("name_ru") or "").strip() or None,
             (form.get("description") or "").strip() or None,
             (form.get("notes") or "").strip() or None,
             bool(form.get("is_abandoned")), my_order, series_id))
        for book_id, pos in positions.items():
            conn.execute("update series_books set my_position = %s where series_id = %s and book_id = %s",
                         (pos, series_id, book_id))

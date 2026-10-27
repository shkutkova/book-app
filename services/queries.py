"""Чтение данных для страниц. Только SELECT: всё, что меняет базу, — в library.py.
Каждая функция получает user_id: библиотека, оценки и прочтения у каждого свои."""
from db import fetch_all, fetch_one
from services.hardcover_api import is_main

STATUS_NAMES = {
    "want_to_read": "Хочу прочитать",
    "reading": "Читаю",
    "finished": "Прочитано",
    "paused": "На паузе",
    "dnf": "Брошено",
    "skipped": "Пропускаю",
}
SERIES_STATUS_NAMES = {
    "in_progress": "В процессе",
    "to_read": "Хочу прочитать",
    "done": "Прочитано",
    "abandoned": "Бросила",
}
WORK_STATUS_NAMES = {
    "in_progress": "В процессе",
    "finished": "Завершён",
    "frozen": "Заморожен",
}

# Общая часть: книга + авторы + её статус у тебя.
# В запросе должен быть join library l ... and l.user_id = %(u)s
BOOK_FIELDS = """
    b.id, b.kind, b.title, b.title_ru, b.cover_url, b.pages,
    l.status, l.rating, l.is_favorite,
    (select string_agg(a.name || case when ba.role = 'translator' then ' (перевод)' else '' end,
                       ', ' order by ba.role, a.name)
       from book_authors ba join authors a on a.id = ba.author_id
      where ba.book_id = b.id) as authors
"""


# ------------------------------------------------------------------ главная

def home(user_id: str) -> dict:
    u = {"u": user_id}
    counts = {r["status"]: r["n"] for r in fetch_all(
        "select status, count(*) as n from library where user_id = %(u)s group by status", u)}
    reading = fetch_all(f"""
        select {BOOK_FIELDS}
        from library l join books b on b.id = l.book_id
        where l.user_id = %(u)s and l.status = 'reading'
        order by b.title""", u)
    # Каждое прочтение — отдельная строка, поэтому перечитывания тоже считаются
    reads = fetch_all("""
        select r.finished_at, b.id as book_id, b.title, b.title_ru, b.cover_url,
               coalesce(b.pages, 0) as pages
        from reads r join books b on b.id = r.book_id
        where r.user_id = %(u)s and r.finished_at is not null
        order by r.finished_at""", u)
    series = fetch_all("""
        select id, name, name_ru, total_books, finished_books
        from series_progress
        where user_id = %(u)s and status = 'in_progress'
        order by is_reading desc, finished_books::float / greatest(total_books, 1) desc, name""", u)
    return {"counts": counts, "reading": reading, "reads": reads, "series": series}


# ------------------------------------------------------------------ серии

def series_list(user_id: str) -> list[dict]:
    """Только серии, где у тебя есть хотя бы одна книга."""
    u = {"u": user_id}
    rows = fetch_all("""
        select sp.*,
               (select string_agg(distinct a.name, ', ')
                  from series_books sb
                  join book_authors ba on ba.book_id = sb.book_id
                  join authors a on a.id = ba.author_id
                 where sb.series_id = sp.id) as authors
        from series_progress sp
        where sp.user_id = %(u)s and sp.my_books > 0
        order by sp.name""", u)
    covers = fetch_all("""
        select o.series_id, b.id, b.title, b.title_ru, b.cover_url, o.status
        from series_books_ordered o join books b on b.id = o.book_id
        where o.user_id = %(u)s
        order by o.series_id, o.sort_position nulls last, b.title""", u)
    by_series: dict[int, list] = {}
    for c in covers:
        by_series.setdefault(c["series_id"], []).append(c)
    for r in rows:
        r["books"] = by_series.get(r["id"], [])
    return rows


def series_detail(user_id: str, series_id: int) -> dict | None:
    p = {"u": user_id, "s": series_id}
    s = fetch_one("""
        select s.id, s.name, s.name_ru, s.description, s.ficbook_id, s.hardcover_id, s.is_completed,
               coalesce(us.is_abandoned, false) as is_abandoned,
               coalesce(us.use_my_order, false) as use_my_order,
               sp.total_books, sp.finished_books, sp.skipped_books, sp.extra_books,
               sp.status as progress_status
        from series s
        join series_progress sp on sp.id = s.id and sp.user_id = %(u)s
        left join user_series us on us.series_id = s.id and us.user_id = %(u)s
        where s.id = %(s)s""", p)
    if not s:
        return None
    s["books"] = fetch_all(f"""
        select {BOOK_FIELDS}, o.official_position, o.my_position, o.sort_position,
               (select max(r.finished_at) from reads r
                 where r.book_id = b.id and r.user_id = %(u)s) as finished_at
        from series_books_ordered o
        join books b on b.id = o.book_id
        left join library l on l.book_id = b.id and l.user_id = %(u)s
        where o.user_id = %(u)s and o.series_id = %(s)s
        order by o.sort_position nulls last, b.title""", p)
    s["authors"] = sorted({a for b in s["books"] if b["authors"] for a in b["authors"].split(", ")})
    # Основные (номер 1, 2, 3 или без номера) и дополнительные (1.5 — повести, рассказы)
    s["extras"] = [b for b in s["books"] if not is_main(b["official_position"])]
    s["books"] = [b for b in s["books"] if is_main(b["official_position"])]
    s["pages"] = sum(b["pages"] or 0 for b in s["books"])
    return s


# ------------------------------------------------------------------ фанфики

def fanfics(user_id: str) -> list[dict]:
    """Фанфики в твоей библиотеке: сначала те, что читаешь, потом по названию."""
    return fetch_all(f"""
        select {BOOK_FIELDS}, b.work_status, b.pairings,
               (select max(r.finished_at) from reads r
                 where r.book_id = b.id and r.user_id = %(u)s) as finished_at
        from library l join books b on b.id = l.book_id
        where l.user_id = %(u)s and b.kind = 'fanfic'
        order by l.status = 'reading' desc, coalesce(b.title_ru, b.title)""", {"u": user_id})


# ------------------------------------------------------------------ книга

def book_detail(user_id: str, book_id: int) -> dict | None:
    p = {"u": user_id, "b": book_id}
    b = fetch_one(f"""
        select {BOOK_FIELDS}, b.description, b.description_ru, b.release_date,
               b.source_url, b.hardcover_slug, b.hardcover_tags,
               b.fandoms, b.pairings, b.work_status, b.words, b.parts, b.ficbook_meta,
               l.book_id is not null as in_library, l.my_genre_id, l.notes
        from books b left join library l on l.book_id = b.id and l.user_id = %(u)s
        where b.id = %(b)s""", p)
    if not b:
        return None
    b["series"] = fetch_all("""
        select s.id, s.name, s.name_ru, o.sort_position,
               (select count(*) from series_books x where x.series_id = s.id) as books_count
        from series_books_ordered o join series s on s.id = o.series_id
        where o.user_id = %(u)s and o.book_id = %(b)s""", p)
    b["reads"] = fetch_all("""
        select id, started_at, finished_at from reads
        where user_id = %(u)s and book_id = %(b)s
        order by coalesce(finished_at, started_at) desc nulls first""", p)
    return b


def genres(user_id: str) -> list[dict]:
    return fetch_all("select id, name, color from my_genres where user_id = %s order by name", (user_id,))

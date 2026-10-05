"""Чтение данных для страниц. Только SELECT: всё, что меняет базу, — в library.py."""
from db import fetch_all, fetch_one

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

# Общая часть: книга + авторы + её статус у тебя
BOOK_FIELDS = """
    b.id, b.title, b.title_ru, b.cover_url, b.pages,
    l.status, l.rating, l.is_favorite,
    (select string_agg(a.name, ', ' order by a.name)
       from book_authors ba join authors a on a.id = ba.author_id
      where ba.book_id = b.id) as authors
"""


# ------------------------------------------------------------------ главная

def home() -> dict:
    counts = {r["status"]: r["n"] for r in fetch_all(
        "select status, count(*) as n from library group by status")}
    reading = fetch_all(f"""
        select {BOOK_FIELDS}
        from library l join books b on b.id = l.book_id
        where l.status = 'reading'
        order by b.title""")
    # Каждое прочтение — отдельная строка, поэтому перечитывания тоже считаются
    reads = fetch_all("""
        select r.finished_at, b.id as book_id, b.title, b.title_ru, b.cover_url,
               coalesce(b.pages, 0) as pages
        from reads r join books b on b.id = r.book_id
        where r.finished_at is not null
        order by r.finished_at""")
    series = fetch_all("""
        select id, name, name_ru, total_books, finished_books
        from series_progress
        where status = 'in_progress'
        order by is_reading desc, finished_books::float / greatest(total_books, 1) desc, name""")
    return {"counts": counts, "reading": reading, "reads": reads, "series": series}


# ------------------------------------------------------------------ серии

def series_list() -> list[dict]:
    rows = fetch_all("""
        select sp.*,
               (select string_agg(distinct a.name, ', ')
                  from series_books sb
                  join book_authors ba on ba.book_id = sb.book_id
                  join authors a on a.id = ba.author_id
                 where sb.series_id = sp.id) as authors
        from series_progress sp
        order by sp.name""")
    covers = fetch_all("""
        select o.series_id, b.id, b.title, b.cover_url, o.status
        from series_books_ordered o join books b on b.id = o.book_id
        order by o.series_id, o.sort_position nulls last, b.title""")
    by_series: dict[int, list] = {}
    for c in covers:
        by_series.setdefault(c["series_id"], []).append(c)
    for r in rows:
        r["books"] = by_series.get(r["id"], [])
    return rows


def series_detail(series_id: int) -> dict | None:
    s = fetch_one("""
        select s.*, sp.total_books, sp.finished_books, sp.skipped_books, sp.status as progress_status
        from series s join series_progress sp on sp.id = s.id
        where s.id = %s""", (series_id,))
    if not s:
        return None
    s["books"] = fetch_all(f"""
        select {BOOK_FIELDS}, o.official_position, o.my_position, o.sort_position,
               (select max(r.finished_at) from reads r where r.book_id = b.id) as finished_at
        from series_books_ordered o
        join books b on b.id = o.book_id
        left join library l on l.book_id = b.id
        where o.series_id = %s
        order by o.sort_position nulls last, b.title""", (series_id,))
    s["authors"] = sorted({a for b in s["books"] if b["authors"] for a in b["authors"].split(", ")})
    s["pages"] = sum(b["pages"] or 0 for b in s["books"])
    return s


# ------------------------------------------------------------------ книга

def book_detail(book_id: int) -> dict | None:
    b = fetch_one(f"""
        select {BOOK_FIELDS}, b.description, b.description_ru, b.release_date,
               b.source_url, b.hardcover_slug, b.hardcover_tags,
               l.book_id is not null as in_library, l.my_genre_id, l.notes
        from books b left join library l on l.book_id = b.id
        where b.id = %s""", (book_id,))
    if not b:
        return None
    b["series"] = fetch_all("""
        select s.id, s.name, s.name_ru, o.sort_position,
               (select count(*) from series_books x where x.series_id = s.id) as books_count
        from series_books_ordered o join series s on s.id = o.series_id
        where o.book_id = %s""", (book_id,))
    b["reads"] = fetch_all("""
        select id, started_at, finished_at from reads
        where book_id = %s order by coalesce(finished_at, started_at) desc nulls first""", (book_id,))
    return b


def genres() -> list[dict]:
    return fetch_all("select id, name, color from my_genres order by name")

"""Книги из Hardcover в каталог: добавить по поиску, обновить уже добавленную.
Вместе с книгой приходят её авторы и серии — со ВСЕМИ книгами серии
(они попадают в каталог, но не в библиотеку: на странице серии — «не добавлена»).

Чтобы не плодить дубли с тем, что пришло из Notion, сначала ищем уже
существующую запись без связи с Hardcover — по названию (без регистра и
знаков препинания) — и связываем её, а не создаём новую."""
import json
from datetime import date

from db import transaction
from services import hardcover_api as hc
from services.library import ValidationError

# Название без регистра, пробелов и знаков препинания — для поиска дублей
NORM = "lower(regexp_replace({}, '[^[:alnum:]]', '', 'g'))"


def _find_or_link(conn, table: str, hc_id: int, name: str, name_col: str, extra: str = "") -> int | None:
    """id записи с этим hardcover_id; иначе — запись с тем же названием без связи (и связываем)."""
    row = conn.execute(f"select id from {table} where hardcover_id = %s", (hc_id,)).fetchone()
    if row:
        return row["id"]
    row = conn.execute(
        f"select id from {table} where hardcover_id is null {extra} "
        f"and {NORM.format(name_col)} = {NORM.format('%s')} order by id limit 1", (name,)).fetchone()
    if row:
        conn.execute(f"update {table} set hardcover_id = %s where id = %s", (hc_id, row["id"]))
        return row["id"]
    return None


def _author(conn, a: dict) -> int:
    author_id = _find_or_link(conn, "authors", a["id"], a["name"], "name")
    if author_id is None:
        author_id = conn.execute("insert into authors (hardcover_id, name) values (%s, %s) returning id",
                                 (a["id"], a["name"])).fetchone()["id"]
    return author_id


def _book(conn, b: dict, full: bool) -> int:
    """Книга из Hardcover -> id в каталоге. full=True — полные данные (описание, жанры),
    иначе только то, что есть в составе серии."""
    # фанфик с таким же названием — не та книга
    book_id = _find_or_link(conn, "books", b["id"], b["title"], "title", "and kind = 'book'")
    cover = (b.get("image") or {}).get("url")
    release = date.fromisoformat(b["release_date"]) if b.get("release_date") else None
    if book_id is None:
        book_id = conn.execute(
            """insert into books (hardcover_id, hardcover_slug, title, pages, release_date, cover_url)
               values (%s, %s, %s, %s, %s, %s) returning id""",
            (b["id"], b.get("slug"), b["title"], b.get("pages") or None, release, cover)).fetchone()["id"]
    else:
        # своё (русское название, своя обложка, страницы из Notion) не перетираем
        conn.execute(
            """update books set hardcover_slug = coalesce(hardcover_slug, %s),
                 pages = coalesce(pages, %s), release_date = coalesce(%s, release_date),
                 cover_url = coalesce(cover_url, %s)
               where id = %s""",
            (b.get("slug"), b.get("pages") or None, release, cover, book_id))
    if full:
        # у фанфика описание с ficbook (перевод) — английское из Hardcover только если своего нет
        conn.execute(
            """update books set hardcover_tags = %s, synced_at = now(),
                 description = case when kind = 'fanfic' then coalesce(description, %s) else %s end
               where id = %s""",
            (json.dumps(hc.tags_of(b.get("cached_tags")), ensure_ascii=False),
             b.get("description"), b.get("description"), book_id))
    for a in hc.authors_of(b):
        conn.execute("insert into book_authors (book_id, author_id) values (%s, %s) on conflict do nothing",
                     (book_id, _author(conn, a)))
    return book_id


def _series(conn, s: dict) -> int:
    series_id = _find_or_link(conn, "series", s["id"], s["name"], "name")
    if series_id is None:
        series_id = conn.execute(
            "insert into series (hardcover_id, name, description, is_completed) values (%s, %s, %s, %s) returning id",
            (s["id"], s["name"], s.get("description"), s.get("is_completed"))).fetchone()["id"]
    else:
        # описание из Notion не перетираем; берём из Hardcover, только если своего нет
        conn.execute("""update series set description = coalesce(description, %s),
                          is_completed = coalesce(%s, is_completed) where id = %s""",
                     (s.get("description"), s.get("is_completed"), series_id))
    for b in s["books"]:
        conn.execute(
            """insert into series_books (series_id, book_id, official_position) values (%s, %s, %s)
               on conflict (series_id, book_id) do update
               set official_position = coalesce(series_books.official_position, excluded.official_position)""",
            (series_id, _book(conn, b, full=False), b["position"]))
    return series_id


def _load(hc_book_id: int) -> tuple[dict, list[tuple[dict, float | None]]]:
    """Книга и её серии (с номером книги в каждой) из Hardcover — все запросы до записи в базу."""
    book = hc.book(hc_book_id)
    if not book:
        raise ValidationError("Такой книги в Hardcover нет")
    series = []
    for bs in book.get("book_series") or []:
        if bs.get("compilation") or not bs.get("series"):
            continue
        s = hc.series(bs["series"]["id"])
        if s:
            series.append((s, bs.get("position")))
    return book, series


def _save(conn, book: dict, series: list) -> int:
    book_id = _book(conn, book, full=True)
    for s, position in series:
        series_id = _series(conn, s)
        # Добавляемая книга — в серии, даже если для её номера Hardcover выбрал другое издание
        conn.execute("""insert into series_books (series_id, book_id, official_position) values (%s, %s, %s)
                        on conflict do nothing""", (series_id, book_id, position))
    return book_id


def add_from_hardcover(user_id: str, hc_book_id: int) -> int:
    """Добавляет книгу (с авторами и сериями) в каталог и в библиотеку как «Хочу прочитать».
    Если книга уже есть — обновляет данные из Hardcover, статус не трогает."""
    try:
        book, series = _load(hc_book_id)
    except hc.HardcoverError as e:
        raise ValidationError(str(e))
    with transaction() as conn:
        book_id = _save(conn, book, series)
        conn.execute("insert into library (user_id, book_id) values (%s, %s) on conflict do nothing",
                     (user_id, book_id))
    return book_id


def refresh_from_hardcover(book_id: int, link_to: int | None = None) -> None:
    """Кнопка «Обновить из Hardcover» на странице книги.
    link_to — связать с этой книгой Hardcover (из поиска «Найти в Hardcover»): тогда
    и обложка берётся из Hardcover, если она там есть.
    Фанфик остаётся фанфиком (ссылка на ficbook, описание перевода); из Hardcover —
    обложка, жанры, автор оригинала. Серии Hardcover к фанфику не добавляем:
    у него свой цикл с ficbook."""
    with transaction() as conn:
        row = conn.execute("select hardcover_id, hardcover_slug, kind from books where id = %s",
                           (book_id,)).fetchone()
    if not row:
        raise ValidationError("Книга не найдена")
    hc_id = link_to or row["hardcover_id"]
    try:
        if not hc_id and row["hardcover_slug"]:
            found = hc.book_by_slug(row["hardcover_slug"])
            hc_id = found and found["id"]
        if not hc_id:
            raise ValidationError("Книга не связана с Hardcover: нажми «Найти в Hardcover» на странице книги")
        book, series = _load(hc_id)
    except hc.HardcoverError as e:
        raise ValidationError(str(e))
    if row["kind"] == "fanfic":
        series = []
    with transaction() as conn:
        taken = conn.execute("""select title from books where (hardcover_id = %s or hardcover_slug = %s)
                                and id <> %s""", (hc_id, book.get("slug"), book_id)).fetchone()
        if taken:
            raise ValidationError(f"Эта книга Hardcover уже связана с «{taken['title']}»")
        if link_to:
            cover = (book.get("image") or {}).get("url")
            conn.execute("""update books set hardcover_id = %s, hardcover_slug = %s,
                              cover_url = coalesce(%s, cover_url) where id = %s""",
                         (hc_id, book.get("slug"), cover, book_id))
        else:
            conn.execute("update books set hardcover_id = %s where id = %s and hardcover_id is null",
                         (hc_id, book_id))
        _save(conn, book, series)


def refresh_series(series_id: int) -> None:
    """Кнопка «Обновить состав серии из Hardcover»: дотягивает книги серии, которых нет."""
    with transaction() as conn:
        row = conn.execute("select hardcover_id from series where id = %s", (series_id,)).fetchone()
    if not row or not row["hardcover_id"]:
        raise ValidationError("Серия не связана с Hardcover — добавь любую её книгу через поиск")
    try:
        s = hc.series(row["hardcover_id"])
    except hc.HardcoverError as e:
        raise ValidationError(str(e))
    if not s:
        raise ValidationError("Серии больше нет в Hardcover")
    with transaction() as conn:
        _series(conn, s)


def known(user_id: str, hc_ids: list[int]) -> dict[int, dict]:
    """Для результатов поиска: какие книги уже в каталоге и в твоей библиотеке."""
    if not hc_ids:
        return {}
    with transaction() as conn:
        rows = conn.execute(
            """select b.hardcover_id, b.id, l.status from books b
               left join library l on l.book_id = b.id and l.user_id = %s
               where b.hardcover_id = any(%s)""", (user_id, hc_ids)).fetchall()
    return {r["hardcover_id"]: r for r in rows}

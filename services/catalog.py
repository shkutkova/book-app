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
from services.ficbook import CYRILLIC, names, positive_int, split_title
from services.library import ValidationError, cover_link

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
    # книги, которые убрала из этой серии вручную, обратно не добавляем
    removed = {r["hardcover_id"] for r in conn.execute(
        "select hardcover_id from series_removed where series_id = %s", (series_id,)).fetchall()}
    for b in s["books"]:
        if b["id"] in removed:
            continue
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


def add_manual(user_id: str, form: dict) -> int:
    """Книга, которой нет в Hardcover: всё из формы. Добавляется в «Хочу прочитать».
    Позже её можно связать с Hardcover кнопкой «Найти в Hardcover»."""
    raw_title = (form.get("title") or "").strip()
    if not raw_title:
        raise ValidationError("Нужно название")
    title, title_ru = split_title(raw_title)
    authors = names(form.get("authors"))
    if not authors:
        raise ValidationError("Укажи автора")
    pages = positive_int(form.get("pages"), "Страницы")
    cover = cover_link(form.get("cover_url"))
    source = (form.get("source_url") or "").strip() or None
    if source and not source.startswith(("http://", "https://")):
        raise ValidationError("Ссылка «Где читать» должна начинаться с http:// или https://")
    description = (form.get("description") or "").strip() or None
    series_name = (form.get("series_name") or "").strip() or None
    position = (form.get("series_position") or "").strip().replace(",", ".")
    try:
        position = float(position) if position else None
    except ValueError:
        raise ValidationError(f"Номер в серии должен быть числом: {position}")

    with transaction() as conn:
        twin = conn.execute(
            f"select id, title from books where kind = 'book' and {NORM.format('title')} = {NORM.format('%s')}",
            (title,)).fetchone()
        if twin:
            # уже в каталоге (например, пришла с серией как «не добавлена») — берём её, без дубля
            conn.execute("insert into library (user_id, book_id) values (%s, %s) on conflict do nothing",
                         (user_id, twin["id"]))
            return twin["id"]
        # русское описание — в description_ru (как из Notion), иначе — description
        ru = description and CYRILLIC.search(description)
        book_id = conn.execute(
            """insert into books (kind, title, title_ru, pages, cover_url, source_url, description, description_ru)
               values ('book', %s, %s, %s, %s, %s, %s, %s) returning id""",
            (title, title_ru, pages, cover, source, None if ru else description, description if ru else None)
        ).fetchone()["id"]
        for name in authors:
            row = conn.execute(f"select id from authors where {NORM.format('name')} = {NORM.format('%s')} "
                               "order by id limit 1", (name,)).fetchone()
            author_id = row["id"] if row else conn.execute(
                "insert into authors (name) values (%s) returning id", (name,)).fetchone()["id"]
            conn.execute("insert into book_authors (book_id, author_id) values (%s, %s) on conflict do nothing",
                         (book_id, author_id))
        if series_name:
            name, name_ru = split_title(series_name)
            row = conn.execute(f"select id from series where {NORM.format('name')} = {NORM.format('%s')} "
                               "order by id limit 1", (name,)).fetchone()
            series_id = row["id"] if row else conn.execute(
                "insert into series (name, name_ru) values (%s, %s) returning id", (name, name_ru)).fetchone()["id"]
            conn.execute("insert into series_books (series_id, book_id, official_position) values (%s, %s, %s)",
                         (series_id, book_id, position))
        conn.execute("insert into library (user_id, book_id) values (%s, %s)", (user_id, book_id))
    return book_id


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

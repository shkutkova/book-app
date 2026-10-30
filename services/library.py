"""Всё, что меняет базу: статус, оценка, прочтения, порядок в серии.
Правила (бизнес-логика) собраны здесь, чтобы страницы их не дублировали.
Личные данные (library, reads, user_series...) всегда меняются только у user_id."""
import re
from datetime import date

import httpx

from db import fetch_one, transaction
from services.hardcover_api import is_main

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


GOOGLE_BOOK = re.compile(r"https?://(?:www\.|books\.)?google\.[a-z.]+/books(?:/edition/[^/]+/|(?:/content)?\?(?:.*&)?id=)([\w-]{12})")


def google_cover(volume_id: str) -> str:
    """Обложка книги Google Books по id — напрямую, без API (у API без ключа квота 0).
    Крупная (zoom=3) есть не у всех: вместо неё Google отдаёт PNG-заглушку — тогда берём обычную."""
    url = f"https://books.google.com/books/content?id={volume_id}&printsec=frontcover&img=1&zoom="
    try:
        r = httpx.head(url + "3", timeout=10, follow_redirects=True)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/jpeg"):
            return url + "3"
    except httpx.HTTPError:
        pass
    return url + "1"


def cover_link(raw: str | None) -> str | None:
    """Ссылка на картинку. Ссылку на страницу книги в Google Books (и маленькую картинку оттуда,
    как в вариантах обложек) превращаем в её крупную обложку."""
    raw = (raw or "").strip()
    if raw and not re.match(r"https?://", raw):
        raise ValidationError("Ссылка на обложку должна начинаться с http:// или https://")
    m = GOOGLE_BOOK.match(raw)
    if m:
        return google_cover(m.group(1))
    return raw or None


DRIVE_FILE = re.compile(r"https://(?:drive|docs)\.google\.com/(?:file/d/|open\?id=|uc\?(?:.*&)?id=)([\w-]{20,})")


def file_links(url: str | None) -> dict | None:
    """Ссылка на свой файл книги -> {open, download}. У Google Диска «скачать» — прямая ссылка
    на файл (без страницы просмотра); у остальных обе ведут по самой ссылке."""
    if not url:
        return None
    m = DRIVE_FILE.match(url)
    if m:
        return {"open": f"https://drive.google.com/file/d/{m.group(1)}/view",
                "download": f"https://drive.google.com/uc?export=download&id={m.group(1)}", "drive": True}
    return {"open": url, "download": url, "drive": False}


def set_file(user_id: str, book_id: int, raw: str | None) -> None:
    """Ссылка на свой файл книги (Google Диск или любая https). Пустая — убрать."""
    url = (raw or "").strip() or None
    if url and not re.match(r"https?://", url):
        raise ValidationError("Ссылка на файл должна начинаться с https://")
    with transaction() as conn:
        updated = conn.execute("update library set file_url = %s where user_id = %s and book_id = %s",
                               (url, user_id, book_id)).rowcount
    if not updated:
        raise ValidationError("Сначала добавь книгу к себе")


def set_cover(book_id: int, raw: str | None) -> None:
    """Обложка, выбранная на странице «Выбрать обложку»."""
    cover = cover_link(raw)
    if not cover:
        raise ValidationError("Не выбрана обложка")
    with transaction() as conn:
        conn.execute("update books set cover_url = %s where id = %s", (cover, book_id))


def save_book(user_id: str, book_id: int, form: dict) -> None:
    """Сохраняет «мою» часть книги. При смене статуса автоматически ведёт прочтения:
    - стала «Читаю» → открывается прочтение с датой начала (сегодня, если не указана);
    - стала «Прочитано» → открытое прочтение закрывается (или создаётся новое) с датой окончания.
    Просто изменить оценку у прочитанной книги — новое прочтение НЕ создаётся.
    Поля, которых нет в форме, не меняются: на странице книги статус, «избранное»
    и настройки — отдельные формы."""
    keep = fetch_one("""select l.status, l.rating, l.is_favorite, l.my_genre_id, l.notes, l.my_description, b.title_ru
                        from books b left join library l on l.book_id = b.id and l.user_id = %s
                        where b.id = %s""", (user_id, book_id)) or {}
    form = {**{k: ("on" if v is True else "" if v in (None, False) else str(v))
                for k, v in keep.items() if k not in form}, **form}
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
        if genre_id and not conn.execute("select 1 from my_genres where id = %s and user_id = %s",
                                         (genre_id, user_id)).fetchone():
            raise ValidationError("Неизвестный жанр")
        old = conn.execute("select status from library where user_id = %s and book_id = %s",
                           (user_id, book_id)).fetchone()
        old_status = old["status"] if old else None
        conn.execute(
            """insert into library (user_id, book_id, status, rating, is_favorite, my_genre_id, notes, my_description)
               values (%s, %s, %s, %s, %s, %s, %s, %s)
               on conflict (user_id, book_id) do update set
                 status = excluded.status, rating = excluded.rating,
                 is_favorite = excluded.is_favorite, my_genre_id = excluded.my_genre_id,
                 notes = excluded.notes, my_description = excluded.my_description""",
            (user_id, book_id, status, rating, bool(form.get("is_favorite")), genre_id,
             (form.get("notes") or "").strip() or None, (form.get("my_description") or "").strip() or None))
        # «Следующая» — только у книг из «Хочу прочитать»: начала читать — отметка снимается
        conn.execute("update library set is_next = false where user_id = %s and book_id = %s and status <> 'want_to_read'",
                     (user_id, book_id))
        conn.execute("update books set title_ru = %s where id = %s",
                     ((form.get("title_ru") or "").strip() or None, book_id))
        # Оригинальное название — только если поле было в форме и не пустое (пустым его не сделать)
        if (form.get("title") or "").strip():
            conn.execute("update books set title = %s where id = %s", (form["title"].strip(), book_id))
        # Книга ↔ фанфик и аннотация — только из настроек (в других формах этих полей нет)
        if form.get("kind") in ("book", "fanfic"):
            conn.execute("update books set kind = %s where id = %s", (form["kind"], book_id))
        if "annotation" in form:
            # Одно поле — видимая аннотация. Правка ложится в description_ru: она показывается первой
            # и «Обновить из Hardcover» её не трогает (там пишется description). Стёрла — пусто совсем
            text = (form.get("annotation") or "").strip() or None
            old = conn.execute("select description, description_ru from books where id = %s", (book_id,)).fetchone()
            if text != (old["description_ru"] or old["description"]):
                conn.execute("update books set description_ru = %s, description = case when %s then null else description end"
                             " where id = %s", (text, text is None, book_id))
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
            """select id, started_at from reads where user_id = %s and book_id = %s and finished_at is null
               order by id desc limit 1""", (user_id, book_id)).fetchone()
        if status == "reading" and not open_read:
            conn.execute("insert into reads (user_id, book_id, started_at) values (%s, %s, %s)",
                         (user_id, book_id, started or date.today()))
        elif status == "finished":
            end = finished or date.today()
            if open_read:
                check_dates(open_read["started_at"], end)
                conn.execute("update reads set finished_at = %s where id = %s", (end, open_read["id"]))
            else:
                conn.execute("""insert into reads (user_id, book_id, started_at, finished_at)
                                values (%s, %s, %s, %s)""", (user_id, book_id, started, end))


def add_to_library(user_id: str, book_id: int) -> None:
    with transaction() as conn:
        conn.execute("insert into library (user_id, book_id) values (%s, %s) on conflict do nothing",
                     (user_id, book_id))


def save_read(user_id: str, book_id: int, read_id: int, form: dict) -> None:
    started = parse_date(form.get("started_at"))
    finished = parse_date(form.get("finished_at"))
    check_dates(started, finished)
    with transaction() as conn:
        conn.execute("""update reads set started_at = %s, finished_at = %s
                        where id = %s and book_id = %s and user_id = %s""",
                     (started, finished, read_id, book_id, user_id))


def add_read(user_id: str, book_id: int, form: dict) -> None:
    """Перечитывание: новое прочтение уже прочитанной книги."""
    started = parse_date(form.get("started_at"))
    finished = parse_date(form.get("finished_at"))
    if not started and not finished:
        raise ValidationError("Укажи хотя бы одну дату")
    check_dates(started, finished)
    if not fetch_one("select 1 from library where user_id = %s and book_id = %s", (user_id, book_id)):
        raise ValidationError("Сначала добавь книгу в библиотеку")
    with transaction() as conn:
        conn.execute("insert into reads (user_id, book_id, started_at, finished_at) values (%s, %s, %s, %s)",
                     (user_id, book_id, started, finished))


def delete_read(user_id: str, book_id: int, read_id: int) -> None:
    with transaction() as conn:
        conn.execute("delete from reads where id = %s and book_id = %s and user_id = %s",
                     (read_id, book_id, user_id))


# ------------------------------------------------------------------ серия

def _lines(raw: str | None) -> list[str]:
    """Поле «по одному на строку» -> список без пустых и без запятых по краям."""
    return [x.strip().strip(",").strip() for x in (raw or "").splitlines() if x.strip().strip(",").strip()]


def save_tags(book_id: int, form: dict) -> None:
    """Метки со страницы книги или фанфика: жанры, настроения, предупреждения
    (как из Hardcover; «Обновить из Hardcover» заменит их)."""
    with transaction() as conn:
        done = conn.execute(
            """update books set hardcover_tags = coalesce(hardcover_tags, '{}'::jsonb)
                 || jsonb_build_object('genres', to_jsonb(%s::text[]), 'moods', to_jsonb(%s::text[]),
                                       'content_warnings', to_jsonb(%s::text[]))
               where id = %s""",
            (_lines(form.get("genres")), _lines(form.get("moods")), _lines(form.get("content_warnings")), book_id))
        if not done.rowcount:
            raise ValidationError("Книга не найдена")


def delete_book(user_id: str, book_id: int) -> str:
    """Убрать книгу из своих: статус, оценка, прочтения, заметки — всё стирается.
    Из общего каталога книга удаляется, если её больше ни у кого нет и она не стоит в серии
    (иначе серия стала бы неполной). Возвращает kind — куда вернуться после удаления."""
    with transaction() as conn:
        b = conn.execute("select kind from books where id = %s", (book_id,)).fetchone()
        if not b:
            raise ValidationError("Книга не найдена")
        authors = [r["author_id"] for r in conn.execute(
            "select author_id from book_authors where book_id = %s", (book_id,)).fetchall()]
        conn.execute("delete from shelf_order where user_id = %s and item = %s", (user_id, f"b{book_id}"))
        conn.execute("delete from library where user_id = %s and book_id = %s", (user_id, book_id))  # прочтения — каскадом
        conn.execute("""delete from books b where b.id = %s
                          and not exists (select 1 from library l where l.book_id = b.id)
                          and not exists (select 1 from series_books sb where sb.book_id = b.id)""", (book_id,))
        # авторы этой книги, у которых не осталось ни одной книги
        conn.execute("""delete from authors a where a.id = any(%s::bigint[])
                          and not exists (select 1 from book_authors ba where ba.author_id = a.id)""", (authors,))
    return b["kind"]


def set_series_favorite(user_id: str, series_id: int, favorite: bool) -> None:
    """Огонёк «Избранное» у серии — только он, остальное в user_series не трогается."""
    with transaction() as conn:
        conn.execute(
            """insert into user_series (user_id, series_id, is_favorite) values (%s, %s, %s)
               on conflict (user_id, series_id) do update set is_favorite = excluded.is_favorite""",
            (user_id, series_id, favorite))


def set_next(user_id: str, book_id: int, on: bool) -> None:
    """Отметка «Следующая»: ставится только книге из «Хочу прочитать»."""
    with transaction() as conn:
        done = conn.execute("""update library set is_next = %s
                               where user_id = %s and book_id = %s and (status = 'want_to_read' or not %s)""",
                            (on, user_id, book_id, on))
        if not done.rowcount:
            raise ValidationError("«Следующей» можно отметить только книгу из «Хочу прочитать»")


SHELVES = ("fav", "reading", "want")


def save_shelf_order(user_id: str, shelf: str, items: list) -> None:
    """Порядок корешков на полке после перетаскивания: items — ключи 'b<id>' / 's<id>' слева направо."""
    if shelf not in SHELVES:
        raise ValidationError("Нет такой полки")
    items = [str(i) for i in items][:200]
    if not all(len(i) > 1 and i[0] in "bs" and i[1:].isdigit() for i in items):
        raise ValidationError("Непонятный порядок")
    with transaction() as conn:
        conn.execute("delete from shelf_order where user_id = %s and shelf = %s", (user_id, shelf))
        for n, item in enumerate(items):
            conn.execute("insert into shelf_order (user_id, shelf, item, pos) values (%s, %s, %s, %s)",
                         (user_id, shelf, item, n))


def save_series(user_id: str, series_id: int, form: dict) -> None:
    """Описание и русское название — общие для серии; «бросила» и свой порядок — твои."""
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
            "update series set name_ru = %s, description = %s where id = %s",
            ((form.get("name_ru") or "").strip() or None,
             (form.get("description") or "").strip() or None, series_id))
        conn.execute(
            """insert into user_series (user_id, series_id, is_abandoned, use_my_order)
               values (%s, %s, %s, %s)
               on conflict (user_id, series_id) do update set
                 is_abandoned = excluded.is_abandoned, use_my_order = excluded.use_my_order""",
            (user_id, series_id, bool(form.get("is_abandoned")), my_order))
        for book_id, pos in positions.items():
            conn.execute(
                """insert into user_series_books (user_id, series_id, book_id, my_position)
                   values (%s, %s, %s, %s)
                   on conflict (user_id, series_id, book_id) do update set my_position = excluded.my_position""",
                (user_id, series_id, book_id, pos))
        _drop_empty_series_books(conn, user_id, series_id)


def _drop_empty_series_books(conn, user_id: str, series_id: int) -> None:
    """Строка без своего номера и без выбора блока ничего не значит — убираем."""
    conn.execute("""delete from user_series_books where user_id = %s and series_id = %s
                      and my_position is null and is_extra is null""", (user_id, series_id))


def _drop_orphan_books(conn, book_ids: list[int]) -> None:
    """Книги, которых нет ни у кого в библиотеке и ни в одной серии, — из каталога (с осиротевшими авторами)."""
    authors = [r["author_id"] for r in conn.execute(
        "select author_id from book_authors where book_id = any(%s::bigint[])", (book_ids,)).fetchall()]
    conn.execute("""delete from books b where b.id = any(%s::bigint[])
                      and not exists (select 1 from library l where l.book_id = b.id)
                      and not exists (select 1 from series_books sb where sb.book_id = b.id)""", (book_ids,))
    conn.execute("""delete from authors a where a.id = any(%s::bigint[])
                      and not exists (select 1 from book_authors ba where ba.author_id = a.id)""", (authors,))


def remove_from_series(series_id: int, book_id: int) -> None:
    """Убрать книгу из серии. Книга из твоей библиотеки остаётся в библиотеке;
    не добавленная (лишнее издание из Hardcover) удаляется из каталога.
    «Обновить из Hardcover» её больше в эту серию не вернёт."""
    with transaction() as conn:
        b = conn.execute("""select b.hardcover_id from series_books sb join books b on b.id = sb.book_id
                            where sb.series_id = %s and sb.book_id = %s""", (series_id, book_id)).fetchone()
        if not b:
            raise ValidationError("Этой книги нет в серии")
        if b["hardcover_id"]:
            conn.execute("insert into series_removed (series_id, hardcover_id) values (%s, %s) on conflict do nothing",
                         (series_id, b["hardcover_id"]))
        conn.execute("delete from series_books where series_id = %s and book_id = %s", (series_id, book_id))
        _drop_orphan_books(conn, [book_id])


def delete_series(series_id: int) -> None:
    """Удалить серию (например, дубль). Книги из библиотеки остаются со статусами и оценками;
    не добавленные книги, которые были только в этой серии, уходят из каталога."""
    with transaction() as conn:
        books = [r["book_id"] for r in conn.execute(
            "select book_id from series_books where series_id = %s", (series_id,)).fetchall()]
        conn.execute("delete from shelf_order where item = %s", (f"s{series_id}",))
        if not conn.execute("delete from series where id = %s", (series_id,)).rowcount:  # связи — каскадом
            raise ValidationError("Серия не найдена")
        _drop_orphan_books(conn, books)


def set_series_extra(user_id: str, series_id: int, book_id: int, extra: bool) -> None:
    """Перенести книгу в «Дополнительно» (extra=True) или в основные. Совпадает с тем,
    что и так следует из официального номера, — свой выбор снимается."""
    with transaction() as conn:
        row = conn.execute("select official_position from series_books where series_id = %s and book_id = %s",
                           (series_id, book_id)).fetchone()
        if not row:
            raise ValidationError("Этой книги нет в серии")
        choice = None if extra == (not is_main(row["official_position"])) else extra
        conn.execute(
            """insert into user_series_books (user_id, series_id, book_id, is_extra) values (%s, %s, %s, %s)
               on conflict (user_id, series_id, book_id) do update set is_extra = excluded.is_extra""",
            (user_id, series_id, book_id, choice))
        _drop_empty_series_books(conn, user_id, series_id)

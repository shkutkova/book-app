"""Перенос книг, серий и авторов из экспорта Notion в базу (Supabase / PostgreSQL).

Запуск:
    python import_notion.py папка_с_csv              — проверка: ничего не пишет, только отчёт
    python import_notion.py папка_с_csv --write      — записать в базу

Нужны три CSV из экспорта Notion (имена файлов можно не переименовывать,
скрипт найдёт их сам): DataBase ..._all.csv, Series ..._all.csv, Authors ..._all.csv.

Строка подключения берётся из .env: DATABASE_URL=postgresql://...
(Supabase → Project Settings → Database → Connection string → URI).

Скрипт можно запускать повторно: записи ищутся по id страницы Notion и
обновляются, а не дублируются.

Ошибочные данные из Notion не переносятся (в отчёте видно, что именно отброшено):
- номер в серии у книги без серии;
- даты начала/окончания у книг, которые ещё не читались;
- ссылки на Goodreads (книга найдётся в Hardcover), остаются только ficbook и т.п.
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# В экспорте Notion даты без года ("Aug 6"), потому что все они в текущем году.
# Если в базе появятся книги за другие годы, этот способ уже не подойдёт.
YEAR = 2026

STATUS = {
    "Finished": "finished",
    "Want to Read": "want_to_read",
    "Reading": "reading",
    "Skip": "skipped",
}
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}

# "Name (https://app.notion.com/p/Slug-<32 символа id>?pvs=21), Name2 (...)"
LINK = re.compile(r"(?:^|,\s)(.+?) \(https://app\.notion\.com/p/[^\s)]*?([0-9a-f]{32})[^\s)]*\)")
CYRILLIC = re.compile(r"[А-Яа-яЁё]")


# --------------------------------------------------------------------- разбор

def links(value: str | None) -> list[tuple[str, str]]:
    """'A (url-id1), B (url-id2)' -> [('A', 'id1'), ('B', 'id2')]"""
    return [(m.group(1).strip(), m.group(2)) for m in LINK.finditer(value or "")]


def split_title(raw: str) -> tuple[str, str | None]:
    """'Vow of Deception | Обет обмана' -> ('Vow of Deception', 'Обет обмана').
    Порядок частей не важен: русской считается та, где кириллица.
    Если разделителя нет, название целиком — оригинальное."""
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 2 or not all(parts):
        return raw.strip(), None
    a, b = parts
    if CYRILLIC.search(a) and not CYRILLIC.search(b):
        a, b = b, a
    return (a, b) if CYRILLIC.search(b) else (raw.strip(), None)


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    m = re.fullmatch(r"([A-Z][a-z]{2}) (\d{1,2})(?:, (\d{4}))?", raw.strip())
    if not m:
        raise ValueError(f"Непонятная дата: {raw!r}")
    return date(int(m.group(3) or YEAR), MONTHS[m.group(1)], int(m.group(2)))


def stars(raw: str | None) -> int | None:
    n = (raw or "").count("⭐")
    return n or None


def own_link(raw: str | None) -> str | None:
    """Ссылку на Goodreads не храним: такие книги есть в Hardcover."""
    if not raw or "goodreads.com" in raw:
        return None
    return raw


def number(raw: str | None) -> float | None:
    return float(raw) if raw and raw.strip() else None


def find_csv(folder: Path, name: str) -> Path:
    found = sorted(folder.glob(f"*{name}*_all.csv"))
    if len(found) != 1:
        sys.exit(f"В {folder} ожидался один файл *{name}*_all.csv, найдено: {len(found)}")
    return found[0]


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [{k: (v.strip() or None) for k, v in row.items()} for row in csv.DictReader(f)]


# --------------------------------------------------------------------- модель

@dataclass
class Book:
    notion_id: str
    title: str
    title_ru: str | None
    description_ru: str | None
    source_url: str | None
    pages: int | None
    author_id: str
    series_id: str | None
    position: float | None
    status: str
    rating: int | None
    is_favorite: bool
    genre: str | None
    started: date | None
    finished: date | None


@dataclass
class Data:
    authors: dict[str, str] = field(default_factory=dict)              # notion_id -> name
    series: dict[str, dict] = field(default_factory=dict)              # notion_id -> {...}
    books: list[Book] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dropped: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


def load(folder: Path) -> Data:
    db = read_csv(find_csv(folder, "DataBase"))
    series_rows = read_csv(find_csv(folder, "Series"))
    author_rows = read_csv(find_csv(folder, "Authors"))
    data = Data()

    # Свой id у книги в экспорте не выгружается, но он есть в ссылках
    # из таблиц авторов и серий: собираем «название -> id».
    book_ids: dict[str, set[str]] = {}
    for rows, col in ((author_rows, "Books"), (series_rows, "Book")):
        for row in rows:
            for name, nid in links(row.get(col)):
                book_ids.setdefault(name, set()).add(nid)

    for row in db:
        for name, nid in links(row.get("Author")):
            data.authors[nid] = name

    # Серии: id берём из ссылки в книге, остальное — из таблицы Series.
    series_by_name = {r["Name"].strip(): r for r in series_rows if r.get("Name")}
    # Запасной поиск: строка Series, в которой перечислена эта книга
    # (на случай, если название серии в таблице Series испорчено).
    series_by_book = {nid: r for r in series_rows for _, nid in links(r.get("Book"))}
    for row in db:
        for name, nid in links(row.get("Series")):
            if nid in data.series:
                continue
            src = series_by_name.get(name)
            if not src:
                ids = book_ids.get(row["Title"].strip(), set())
                src = next((series_by_book[i] for i in ids if i in series_by_book), {})
                if src:
                    data.warnings.append(
                        f"Серия «{name}»: в таблице Series у неё другое название "
                        f"({src.get('Name')!r}) — взяла название из книги")
                else:
                    data.warnings.append(f"Серия «{name}» не найдена в таблице Series — создам без комментария")
            title, title_ru = split_title(name)
            data.series[nid] = {"name": title, "name_ru": title_ru, "notes": src.get("Comment")}

    for row in db:
        raw_title = row["Title"]
        ids = book_ids.get(raw_title.strip(), set())
        if len(ids) != 1:
            data.warnings.append(f"Книга «{raw_title}»: не удалось определить id в Notion — пропущена")
            continue
        author = links(row.get("Author"))
        series = links(row.get("Series"))
        if len(author) != 1:
            data.warnings.append(f"Книга «{raw_title}»: авторов {len(author)}, ожидался 1 — пропущена")
            continue
        title, title_ru = split_title(raw_title)
        status = STATUS.get(row.get("Status") or "")
        if not status:
            data.warnings.append(f"Книга «{raw_title}»: неизвестный статус {row.get('Status')!r} — пропущена")
            continue
        book = Book(
            notion_id=ids.pop(), title=title, title_ru=title_ru,
            description_ru=row.get("Summary"), source_url=own_link(row.get("Link")),
            pages=int(float(row["Total pages"])) if row.get("Total pages") else None,
            author_id=author[0][1],
            series_id=series[0][1] if series else None,
            position=number(row.get("Num. in series")),
            status=status, rating=stars(row.get("Rating")),
            is_favorite=bool(row.get("BEST")), genre=row.get("Genre"),
            started=parse_date(row.get("Date started")),
            finished=parse_date(row.get("Date finished")),
        )
        clean(book, raw_title, data.dropped)
        data.books.append(book)
    return data


def clean(b: Book, raw: str, dropped: dict[str, list[str]]) -> None:
    """Отбрасывает ошибочные данные и запоминает, что отброшено (для отчёта)."""
    if b.position is not None and not b.series_id:
        dropped["Номер в серии без серии — номер не перенесён"].append(raw)
        b.position = None
    if b.status not in ("finished", "reading") and (b.started or b.finished):
        dropped["Даты у книги, которую ещё не читала, — даты не перенесены"].append(raw)
        b.started = b.finished = None
    if b.status == "reading" and b.finished:
        dropped["«Читаю», но есть дата окончания — дата окончания не перенесена"].append(raw)
        b.finished = None
    if b.started and b.finished and b.finished < b.started:
        dropped["Окончание раньше начала — дата начала не перенесена"].append(raw)
        b.started = None
    if b.status == "finished" and not b.finished:
        dropped["Прочитано, но нет даты окончания — не попадёт в статистику по месяцам"].append(raw)


# --------------------------------------------------------------------- отчёт

def report(data: Data) -> None:
    from collections import Counter
    print(f"Авторов: {len(data.authors)}")
    print(f"Серий:   {len(data.series)}")
    print(f"Книг:    {len(data.books)}")
    print("  по статусам:", dict(Counter(b.status for b in data.books)))
    print("  по жанрам:  ", dict(Counter(b.genre for b in data.books)))
    print(f"  с русским названием: {sum(1 for b in data.books if b.title_ru)}")
    print(f"  в сериях: {sum(1 for b in data.books if b.series_id)}, избранных 🔥: {sum(b.is_favorite for b in data.books)}")
    reads = [b for b in data.books if b.status in ("finished", "reading")]
    print(f"Прочтений: {len(reads)}")
    by_month = Counter(b.finished.strftime("%Y-%m") for b in data.books if b.finished)
    print("  прочитано по месяцам:", dict(sorted(by_month.items())))
    print(f"  ссылок не из Goodreads (ficbook и т.п.): {sum(1 for b in data.books if b.source_url)}")
    if data.warnings:
        print(f"\nЗамечания ({len(data.warnings)}):")
        for w in data.warnings:
            print("  -", w)
    for reason, titles in data.dropped.items():
        print(f"\n{reason} ({len(titles)}):")
        print("  " + ", ".join(f"«{t}»" for t in titles))


# --------------------------------------------------------------------- запись

def write(data: Data, url: str) -> None:
    import psycopg  # pip install "psycopg[binary]"

    # prepare_threshold=None: без подготовленных запросов, иначе ломается
    # пул подключений Supabase (адрес с портом 6543).
    with psycopg.connect(url, prepare_threshold=None) as conn, conn.cursor() as cur:
        genres = dict(cur.execute("select name, id from my_genres").fetchall())
        for g in {b.genre for b in data.books if b.genre} - genres.keys():
            genres[g] = cur.execute(
                "insert into my_genres (name) values (%s) returning id", (g,)).fetchone()[0]

        authors = {}
        for nid, name in data.authors.items():
            authors[nid] = cur.execute(
                """insert into authors (notion_id, name) values (%s, %s)
                   on conflict (notion_id) do update set name = excluded.name
                   returning id""", (nid, name)).fetchone()[0]

        series = {}
        for nid, s in data.series.items():
            series[nid] = cur.execute(
                """insert into series (notion_id, name, name_ru, notes) values (%s, %s, %s, %s)
                   on conflict (notion_id) do update
                   set name = excluded.name, name_ru = excluded.name_ru, notes = excluded.notes
                   returning id""", (nid, s["name"], s["name_ru"], s["notes"])).fetchone()[0]

        for b in data.books:
            book_id = cur.execute(
                """insert into books (notion_id, title, title_ru, description_ru, source_url, pages)
                   values (%s, %s, %s, %s, %s, %s)
                   on conflict (notion_id) do update set
                     title = excluded.title, title_ru = excluded.title_ru,
                     description_ru = excluded.description_ru,
                     source_url = excluded.source_url, pages = excluded.pages
                   returning id""",
                (b.notion_id, b.title, b.title_ru, b.description_ru, b.source_url, b.pages),
            ).fetchone()[0]

            cur.execute("""insert into book_authors (book_id, author_id) values (%s, %s)
                           on conflict do nothing""", (book_id, authors[b.author_id]))
            if b.series_id:
                cur.execute(
                    """insert into series_books (series_id, book_id, official_position)
                       values (%s, %s, %s)
                       on conflict (series_id, book_id)
                       do update set official_position = excluded.official_position""",
                    (series[b.series_id], book_id, b.position))

            cur.execute(
                """insert into library (book_id, status, rating, is_favorite, my_genre_id)
                   values (%s, %s, %s, %s, %s)
                   on conflict (book_id) do update set
                     status = excluded.status, rating = excluded.rating,
                     is_favorite = excluded.is_favorite, my_genre_id = excluded.my_genre_id""",
                (book_id, b.status, b.rating, b.is_favorite, genres.get(b.genre)))

            # Прочтения из Notion перезаписываются целиком при повторном запуске.
            cur.execute("delete from reads where book_id = %s", (book_id,))
            if b.status in ("finished", "reading"):
                cur.execute("insert into reads (book_id, started_at, finished_at) values (%s, %s, %s)",
                            (book_id, b.started, b.finished))
        conn.commit()
    print("\nГотово: данные записаны в базу.")


# ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт книг из Notion")
    parser.add_argument("folder", type=Path, help="папка с CSV из экспорта Notion")
    parser.add_argument("--write", action="store_true", help="записать в базу (без него — только отчёт)")
    args = parser.parse_args()

    data = load(args.folder)
    report(data)
    if not args.write:
        print("\nЭто проверка, в базу ничего не записано. Для записи добавь --write")
        return

    from dotenv import load_dotenv
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("Не задана переменная DATABASE_URL в .env")
    write(data, url)


if __name__ == "__main__":
    main()

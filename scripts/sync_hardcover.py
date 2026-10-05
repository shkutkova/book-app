"""Связывает книги из твоей базы с Hardcover и подтягивает оттуда обложку, описание,
жанры, настроения и предупреждения. Твои поля (русское название, статус, оценка,
даты, избранное, жанр) НЕ меняются.

Запуск (из корня проекта, venv включён):
    python scripts/sync_hardcover.py              — проверка: ищет совпадения, ничего не пишет
    python scripts/sync_hardcover.py --write      — записать уверенные совпадения
    python scripts/sync_hardcover.py --write --with-unsure — записать и сомнительные

Какие книги обрабатываются:
- ещё не связанные с Hardcover;
- кроме фанфиков (жанр Fan Fiction или есть своя ссылка, например ficbook).
Если книге на её странице вписана ссылка на Hardcover — берётся ровно эта книга, без поиска.

Hardcover ограничивает частоту запросов, поэтому скрипт делает паузу между книгами
(на ~200 книг уйдёт несколько минут). Повторный запуск безопасен.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import fetch_all, transaction  # noqa: E402

URL = "https://api.hardcover.app/v1/graphql"
PAUSE = 1.2  # секунд между запросами

SEARCH = """
query ($q: String!) {
  search(query: $q, query_type: "Book", per_page: 5, page: 1) { results }
}"""
DETAILS = """
query ($where: books_bool_exp!) {
  books(where: $where, limit: 1) {
    id slug title description pages
    image { url }
    contributions { author { name } }
    cached_tags
  }
}"""
TAG_GROUPS = {"Genre": "genres", "Mood": "moods", "Content Warning": "content_warnings"}


# ------------------------------------------------------------------ Hardcover

class Hardcover:
    def __init__(self, token: str):
        if not token.lower().startswith("bearer "):
            token = "Bearer " + token
        self.client = httpx.Client(timeout=30, headers={
            "Authorization": token, "User-Agent": "BookApp/0.1 (personal)"})

    def query(self, q: str, variables: dict) -> dict:
        for attempt in range(3):
            r = self.client.post(URL, json={"query": q, "variables": variables})
            if r.status_code == 429:  # слишком часто — ждём и пробуем ещё
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("errors"):
                raise RuntimeError(f"Hardcover вернул ошибку: {data['errors']}")
            time.sleep(PAUSE)
            return data["data"]
        raise RuntimeError("Hardcover не отвечает: слишком много запросов подряд")

    def search(self, text: str) -> list[dict]:
        results = self.query(SEARCH, {"q": text})["search"]["results"]
        if isinstance(results, str):
            results = json.loads(results)
        return [h["document"] for h in results.get("hits", [])]

    def details(self, *, book_id: int | None = None, slug: str | None = None) -> dict | None:
        where = {"id": {"_eq": book_id}} if book_id else {"slug": {"_eq": slug}}
        books = self.query(DETAILS, {"where": where})["books"]
        return books[0] if books else None


# ------------------------------------------------------------------ сравнение

def norm(text: str | None) -> str:
    """'The Serpent & the Wings of Night!' -> 'serpent and the wings of night'"""
    text = (text or "").lower().replace("&", " and ").replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"^(the|a|an)\s+", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def title_match(mine: str, theirs: str) -> bool:
    """Точное совпадение или совпадение без подзаголовка ('Title: A Novel')."""
    a, b = norm(mine), norm(theirs)
    if not a or not b:
        return False
    return a == b or b.startswith(a + " ") and ":" in theirs or a.startswith(b + " ") and ":" in mine


def author_match(mine: list[str], theirs: list[str]) -> bool:
    """Совпадает хотя бы один автор: целиком или по фамилии (для 'S.T. Abby' / 'ST Abby')."""
    theirs_n = [norm(t) for t in theirs or []]
    for m in map(norm, mine):
        last = m.split()[-1] if m else ""
        if any(m == t or (last and t.split() and t.split()[-1] == last) for t in theirs_n):
            return True
    return False


def pick(book: dict, hits: list[dict]) -> tuple[dict | None, str]:
    """Возвращает (найденная книга, уверенность: 'sure' | 'unsure' | 'none')."""
    authors = book["authors"] or []
    sure = [h for h in hits if title_match(book["title"], h.get("title", ""))
            and author_match(authors, h.get("author_names") or [])]
    if sure:
        return sure[0], "sure"
    # Совпал только автор — не считаем: у одного автора бывают десятки книг
    unsure = [h for h in hits if title_match(book["title"], h.get("title", ""))]
    return (unsure[0], "unsure") if unsure else (None, "none")


def tags_from(cached_tags) -> dict:
    """cached_tags Hardcover -> {"genres": [...], "moods": [...], "content_warnings": [...]}
    Сортировка — по тому, сколько читателей поставили тег; берём самые частые."""
    out = {}
    if isinstance(cached_tags, str):
        cached_tags = json.loads(cached_tags)
    if not isinstance(cached_tags, dict):
        return out
    for category, key in TAG_GROUPS.items():
        items = [i for i in cached_tags.get(category) or [] if isinstance(i, dict) and i.get("tag")]
        items.sort(key=lambda i: -(i.get("count") or 0))
        if items:
            out[key] = [i["tag"] for i in items[:8]]
    return out


# ------------------------------------------------------------------ работа с базой

def books_to_sync() -> list[dict]:
    return fetch_all("""
        select b.id, b.title, b.title_ru, b.pages, b.hardcover_slug,
               array_remove(array_agg(a.name), null) as authors
        from books b
        left join book_authors ba on ba.book_id = b.id
        left join authors a on a.id = ba.author_id
        left join library l on l.book_id = b.id
        left join my_genres g on g.id = l.my_genre_id
        where b.hardcover_id is null
          and b.source_url is null
          and coalesce(g.name, '') <> 'Fan Fiction'
        group by b.id
        order by b.title""")


def save(book: dict, hc: dict) -> None:
    with transaction() as conn:
        taken = conn.execute("select id, title from books where hardcover_id = %s and id <> %s",
                             (hc["id"], book["id"])).fetchone()
        if taken:
            raise RuntimeError(f"эта книга Hardcover уже связана с «{taken['title']}»")
        conn.execute(
            """update books set
                 hardcover_id = %s, hardcover_slug = %s,
                 cover_url = coalesce(cover_url, %s),
                 description = %s,
                 pages = coalesce(pages, %s),
                 hardcover_tags = %s,
                 synced_at = now()
               where id = %s""",
            (hc["id"], hc.get("slug"), (hc.get("image") or {}).get("url"), hc.get("description"),
             hc.get("pages"), json.dumps(tags_from(hc.get("cached_tags")), ensure_ascii=False),
             book["id"]))


# ------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Подтянуть обложки и данные из Hardcover")
    parser.add_argument("--write", action="store_true", help="записать в базу")
    parser.add_argument("--with-unsure", action="store_true", help="записать и сомнительные совпадения")
    parser.add_argument("--limit", type=int, help="обработать только первые N книг (для пробы)")
    args = parser.parse_args()

    load_dotenv()
    token = os.getenv("HARDCOVER_TOKEN")
    if not token:
        sys.exit("Не задана переменная HARDCOVER_TOKEN в .env")
    hc = Hardcover(token)

    books = books_to_sync()[: args.limit]
    print(f"Книг для поиска в Hardcover: {len(books)}\n")
    found = {"sure": [], "unsure": [], "none": [], "error": []}

    for i, book in enumerate(books, 1):
        label = f"«{book['title']}» ({', '.join(book['authors'])})"
        try:
            if book["hardcover_slug"]:  # ссылку вписали вручную на странице книги
                match = hc.details(slug=book["hardcover_slug"])
                level = "sure" if match else "none"
            else:
                hit, level = pick(book, hc.search(f"{book['title']} {' '.join(book['authors'])}"))
                if level == "none":  # второй шанс: только по названию
                    hit, level = pick(book, hc.search(book["title"]))
                match = hc.details(book_id=int(hit["id"])) if hit else None
            if not match:
                level = "none"
        except Exception as e:  # одна проблемная книга не должна останавливать остальные
            found["error"].append(f"{label}: {e}")
            continue

        if match:
            hc_authors = ", ".join(c["author"]["name"] for c in match.get("contributions") or [] if c.get("author"))
            line = f"{label} → «{match['title']}» ({hc_authors}) https://hardcover.app/books/{match.get('slug')}"
        else:
            line = label
        found[level].append(line)
        print(f"[{i}/{len(books)}] {'✅' if level == 'sure' else '❓' if level == 'unsure' else '—'} {line}")

        if args.write and match and (level == "sure" or args.with_unsure):
            try:
                save(book, match)
            except Exception as e:
                found["error"].append(f"{label}: не записано — {e}")

    print(f"\nУверенно найдено: {len(found['sure'])}")
    print(f"Сомнительно (название совпало, автор — нет): {len(found['unsure'])}")
    for line in found["unsure"]:
        print("  ❓", line)
    print(f"Не найдено: {len(found['none'])}")
    for line in found["none"]:
        print("  —", line)
    if found["error"]:
        print(f"Ошибки: {len(found['error'])}")
        for line in found["error"]:
            print("  ⚠️", line)
    if not args.write:
        print("\nЭто проверка, в базу ничего не записано. Для записи добавь --write")
    elif not args.with_unsure and found["unsure"]:
        print("\nСомнительные не записаны. Проверь ссылки выше: если всё верно — запусти с --write --with-unsure,"
              "\nесли нет — впиши правильную ссылку Hardcover на странице книги и запусти ещё раз.")


if __name__ == "__main__":
    main()

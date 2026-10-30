"""Варианты обложки для книги из открытых источников — пользователь выбирает сам
(автоматически не ставим: обложки бывают неудачные).

- Hardcover — обложки других изданий той же книги (если книга связана с Hardcover);
- Open Library — по названию и автору;
- Google Books — по названию и автору, и по русскому названию (там бывают русские издания).
  Без ключа у Google общая дневная квота и он часто отвечает 429; GOOGLE_BOOKS_KEY в .env —
  свой бесплатный ключ. Источник, который не ответил, просто пропускается."""
import os
from concurrent.futures import ThreadPoolExecutor

import httpx

from services import hardcover_api as hc
from services.ficbook import CYRILLIC

HEADERS = {"User-Agent": "BookApp/0.1 (personal reading tracker)"}

EDITIONS = """
query ($id: Int!) {
  books_by_pk(id: $id) {
    editions(where: {image_id: {_is_null: false}}, order_by: {users_count: desc}, limit: 24) {
      title users_count language { language } image { url }
    }
  }
}"""


def _hardcover(hc_id: int) -> list[dict]:
    book = hc._query(EDITIONS, {"id": hc_id}).get("books_by_pk") or {}
    return [{"url": e["image"]["url"], "source": "Hardcover",
             "label": ", ".join(filter(None, [e.get("title"), (e.get("language") or {}).get("language")]))}
            for e in book.get("editions") or [] if (e.get("image") or {}).get("url")]


def _open_library(title: str, author: str | None) -> list[dict]:
    params = {"title": title, "limit": 12, "fields": "title,cover_i,first_publish_year"}
    if author:
        params["author"] = author
    r = httpx.get("https://openlibrary.org/search.json", params=params, timeout=20, headers=HEADERS)
    r.raise_for_status()
    return [{"url": f"https://covers.openlibrary.org/b/id/{d['cover_i']}-L.jpg?default=false", "source": "Open Library",
             "label": " · ".join(str(x) for x in (d.get("title"), d.get("first_publish_year")) if x)}
            for d in r.json().get("docs", []) if d.get("cover_i")]


def _google(query: str) -> list[dict]:
    params = {"q": query, "maxResults": 12, "printType": "books"}
    if os.getenv("GOOGLE_BOOKS_KEY"):
        params["key"] = os.getenv("GOOGLE_BOOKS_KEY")
    r = httpx.get("https://www.googleapis.com/books/v1/volumes", params=params, timeout=20, headers=HEADERS)
    r.raise_for_status()
    out = []
    for item in r.json().get("items", []):
        info = item.get("volumeInfo", {})
        link = (info.get("imageLinks") or {}).get("thumbnail")
        if link:
            # https и без «загнутого уголка», который Google дорисовывает
            link = link.replace("http://", "https://").replace("&edge=curl", "")
            authors = ", ".join(info.get("authors") or [])
            out.append({"url": link, "source": "Google Books", "authors": authors, "title": info.get("title") or "",
                        "label": " · ".join(filter(None, [info.get("title"), authors, info.get("language"),
                                                          (info.get("publishedDate") or "")[:4]]))})
    return out


def _google_ru(title: str, author: str | None) -> list[dict]:
    """Русская книга. intitle:"…" с кириллицей у Google не находит ничего, а на запрос из нескольких
    русских слов он часто отвечает 503 — пробуем «название автор», потом только название.
    Книги этого автора — первыми."""
    error = None
    for q in filter(None, [f"{title} {author}" if author else None, title]):
        try:
            found = _google(q)
        except httpx.HTTPError as e:
            error = e
            continue
        if found:
            surname = (author or "").split()[-1].lower() if author else ""
            return sorted(found, key=lambda c: surname not in c["authors"].lower()) if surname else found
    if error:
        raise error
    return []


def candidates(book: dict) -> tuple[list[dict], list[str]]:
    """(варианты обложек, источники, которые не ответили). book — из queries.book_detail."""
    # первый автор (авторы идут раньше переводчиков); переводчик для поиска не годится
    first = (book.get("authors") or "").split(",")[0].strip()
    author = first if first and "(перевод)" not in first else None
    jobs = {}
    if book.get("hardcover_id"):
        jobs["Hardcover"] = lambda: _hardcover(book["hardcover_id"])
    jobs["Open Library"] = lambda: _open_library(book["title"], author)
    if not CYRILLIC.search(book["title"]):
        jobs["Google Books"] = lambda: _google(f'intitle:"{book["title"]}"' + (f' inauthor:"{author}"' if author else ""))
    ru_title = next((t for t in (book.get("title_ru"), book["title"]) if t and CYRILLIC.search(t)), None)
    if ru_title:
        jobs["Google Books (рус.)"] = lambda: _google_ru(ru_title, author)

    found, failed = [], []
    with ThreadPoolExecutor(len(jobs)) as pool:
        futures = {name: pool.submit(job) for name, job in jobs.items()}
        for name, future in futures.items():
            try:
                found += future.result()
            except (httpx.HTTPError, hc.HardcoverError, ValueError, KeyError):
                failed.append(name)
    seen, unique = {book.get("cover_url")}, []
    for c in found:
        if c["url"] not in seen:
            seen.add(c["url"])
            unique.append(c)
    return unique, failed

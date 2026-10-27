"""Hardcover: поиск книг, данные книги и состав серии (синхронно, для страниц приложения).
Токен — HARDCOVER_TOKEN из .env (достаточно прав только на чтение).
Запросы идут только с сервера: в браузер токен не попадает."""
import json
import os

import httpx

URL = "https://api.hardcover.app/v1/graphql"


class HardcoverError(RuntimeError):
    """Hardcover не ответил или ответил ошибкой — текст показывается на странице."""


def _query(query: str, variables: dict | None = None) -> dict:
    token = os.getenv("HARDCOVER_TOKEN")
    if not token:
        raise HardcoverError("Не задан HARDCOVER_TOKEN в .env")
    if not token.lower().startswith("bearer "):
        token = "Bearer " + token
    try:
        r = httpx.post(URL, json={"query": query, "variables": variables or {}}, timeout=20,
                       headers={"Authorization": token, "User-Agent": "BookApp/0.1 (personal)"})
    except httpx.HTTPError as e:
        raise HardcoverError(f"Hardcover не отвечает: {e}")
    if r.status_code == 429:
        raise HardcoverError("Слишком много запросов к Hardcover — подожди минуту")
    if r.status_code != 200:
        raise HardcoverError(f"Hardcover ответил ошибкой {r.status_code}")
    data = r.json()
    if data.get("errors"):
        raise HardcoverError(f"Hardcover: {data['errors'][0].get('message')}")
    return data["data"]


SEARCH = """
query ($q: String!) {
  search(query: $q, query_type: "Book", per_page: 12, page: 1) { results }
}"""

BOOK_FIELDS = """
  id slug title description pages release_date cached_tags
  image { url }
  contributions { contribution author { id name } }
  book_series { position featured compilation series { id name } }
"""
BOOK = "query ($id: Int!) { books(where: {id: {_eq: $id}}, limit: 1) {" + BOOK_FIELDS + "} }"
BOOK_BY_SLUG = "query ($slug: String!) { books(where: {slug: {_eq: $slug}}, limit: 1) { id } }"

SERIES = """
query ($id: Int!) {
  series(where: {id: {_eq: $id}}, limit: 1) {
    id name description is_completed primary_books_count
    book_series(order_by: {position: asc}) {
      position featured compilation
      book { id slug title pages release_date canonical_id users_count image { url }
             contributions { contribution author { id name } } }
    }
  }
}"""

TAG_GROUPS = {"Genre": "genres", "Mood": "moods", "Content Warning": "content_warnings"}


def search(text: str) -> list[dict]:
    results = _query(SEARCH, {"q": text})["search"]["results"]
    if isinstance(results, str):
        results = json.loads(results)
    out = []
    for hit in results.get("hits", []):
        d = hit["document"]
        out.append({
            "id": int(d["id"]),
            "title": d.get("title"),
            "authors": ", ".join(d.get("author_names") or []),
            "year": d.get("release_year"),
            "pages": d.get("pages"),
            "cover": (d.get("image") or {}).get("url"),
            "series": ", ".join(d.get("series_names") or []),
            "users": d.get("users_count") or 0,
        })
    return out


def authors_of(book: dict) -> list[dict]:
    """Только авторы: переводчики, иллюстраторы и чтецы не нужны."""
    return [c["author"] for c in book.get("contributions") or []
            if c.get("author") and c.get("contribution") in (None, "", "Author")]


def tags_of(cached_tags) -> dict:
    """cached_tags -> {"genres": [...], "moods": [...], "content_warnings": [...]} (самые частые)."""
    if isinstance(cached_tags, str):
        cached_tags = json.loads(cached_tags)
    out = {}
    for category, key in TAG_GROUPS.items():
        items = [i for i in (cached_tags or {}).get(category) or [] if isinstance(i, dict) and i.get("tag")]
        items.sort(key=lambda i: -(i.get("count") or 0))
        if items:
            out[key] = [i["tag"] for i in items[:8]]
    return out


def book(book_id: int) -> dict | None:
    rows = _query(BOOK, {"id": book_id})["books"]
    return rows[0] if rows else None


def book_by_slug(slug: str) -> dict | None:
    rows = _query(BOOK_BY_SLUG, {"slug": slug})["books"]
    return rows[0] if rows else None


def series(series_id: int) -> dict | None:
    """Серия с ОДНОЙ книгой на каждый номер. В Hardcover в серии лежат и переводы,
    и сборники «книги 1–3», и переиздания — их отбрасываем:
    сборники не берём, переиздания (canonical_id) не берём, из оставшихся
    на номер — отмеченная featured, иначе самая популярная."""
    rows = _query(SERIES, {"id": series_id})["series"]
    if not rows:
        return None
    s = rows[0]
    best: dict = {}
    for bs in s.get("book_series") or []:
        b = bs.get("book") or {}
        if bs.get("compilation") or b.get("canonical_id") or bs.get("position") is None:
            continue
        key = float(bs["position"])
        score = (bool(bs.get("featured")), b.get("users_count") or 0)
        if key not in best or score > best[key][0]:
            best[key] = (score, b)
    s["books"] = [{"position": pos, **b} for pos, (_, b) in sorted(best.items())]
    return s


def is_main(position) -> bool:
    """Основная книга серии — целый номер (1, 2, 3). 1.5, 0.5 — дополнительные.
    Книги без номера считаем основными: номер просто не указан."""
    return position is None or float(position) == int(float(position))

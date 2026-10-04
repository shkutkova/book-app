"""Страница книги: /book/<slug>  (например /book/insatiable-2023).
Логика здесь, внешний вид в templates/book.html: дизайн можно менять, не трогая этот файл."""
import html
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from hardcover import gql

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

BOOK_QUERY = """
query ($slug: String!) {
  books(where: {slug: {_eq: $slug}}, limit: 1) {
    id title subtitle headline description pages release_year
    rating ratings_count
    image { url }
    contributions { author { name } }
    featured_book_series { position series { id name books_count } }
    cached_tags
  }
}
"""

# твоя оценка и статус этой книги (отдельным запросом, чтобы его сбой не ломал страницу)
MINE_QUERY = """
query ($id: Int!) {
  me { user_books(where: {book_id: {_eq: $id}}, limit: 1) { status_id rating } }
}
"""

STATUS = {1: "Хочу прочитать", 2: "Читаю", 3: "Прочитано", 4: "На паузе", 5: "Брошено"}
GROUP_NAMES = {
    "Genre": "Жанры", "Mood": "Настроение", "Tag": "Теги",
    "Content Warning": "Предупреждения",
}


def clean_text(text: str | None) -> str:
    """Описание может содержать HTML-теги: превращаем в обычный текст."""
    if not text:
        return ""
    text = re.sub(r"<\s*br\s*/?>|</p>", "\n", text, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def tag_groups(raw) -> dict:
    """cached_tags -> {"Жанры": ["Fantasy", ...], "Настроение": [...]}"""
    groups = {}
    if not isinstance(raw, dict):
        return groups
    for category, items in raw.items():
        items = [i for i in (items or []) if i]
        items.sort(key=lambda i: -(i.get("count") or 0) if isinstance(i, dict) else 0)
        names = [(i.get("tag") if isinstance(i, dict) else str(i)) for i in items]
        names = [n for n in names if n]
        if names:
            groups[GROUP_NAMES.get(category, category)] = names
    return groups


@router.get("/book/{slug}", response_class=HTMLResponse)
async def book_page(request: Request, slug: str, debug: bool = False):
    data = await gql(BOOK_QUERY, {"slug": slug})
    if debug:  # «сырой» ответ, чтобы проверить названия полей
        return JSONResponse(data)

    books = data["data"]["books"]
    if not books:
        raise HTTPException(404, "Книга не найдена")
    b = books[0]

    mine = None
    try:
        me = (await gql(MINE_QUERY, {"id": b["id"]}))["data"]["me"]
        me = me[0] if isinstance(me, list) else me
        if me["user_books"]:
            ub = me["user_books"][0]
            mine = {"status": STATUS.get(ub["status_id"], ""), "rating": ub.get("rating")}
    except Exception:
        mine = None  # не страшно: страница откроется и без твоей оценки

    link = b.get("featured_book_series") or {}
    series = link.get("series")
    authors = list(dict.fromkeys(
        c["author"]["name"] for c in b["contributions"] if c.get("author")
    ))

    return templates.TemplateResponse(request, "book.html", {
        "b": b,
        "cover": (b.get("image") or {}).get("url"),
        "authors": authors,
        "series": series,
        "position": link.get("position"),
        "description": clean_text(b.get("description")),
        "groups": tag_groups(b.get("cached_tags")),
        "mine": mine,
    })

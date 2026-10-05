"""Страницы приложения. Здесь только «какой адрес что показывает»:
данные берутся из services/queries.py, изменения — через services/library.py."""
import json
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from services import library, queries

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]


def ru_date(d: date | None) -> str:
    if not d:
        return ""
    text = f"{d.day} {MONTHS_GEN[d.month - 1]}"
    return text if d.year == date.today().year else f"{text} {d.year}"


def stars(rating) -> str:
    if rating is None:
        return ""
    full = int(rating)
    return "★" * full + ("½" if rating - full else "")


def position(p) -> str:
    """1.00 -> «1», 0.50 -> «0.5»"""
    return "" if p is None else f"{float(p):g}"


templates.env.filters.update(ru_date=ru_date, stars=stars, position=position)
templates.env.globals.update(STATUS=queries.STATUS_NAMES, SERIES_STATUS=queries.SERIES_STATUS_NAMES)


def back(url: str, error: str | None = None) -> RedirectResponse:
    """После сохранения возвращаемся на страницу (303 — чтобы F5 не отправил форму повторно)."""
    return RedirectResponse(url + ("?" + urlencode({"error": error}) if error else ""), status_code=303)


# ------------------------------------------------------------------ главная

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    data = queries.home()
    reads = [{"d": r["finished_at"].isoformat(), "id": r["book_id"], "t": r["title_ru"] or r["title"],
              "c": r["cover_url"], "p": r["pages"]} for r in data["reads"]]
    return templates.TemplateResponse(request, "home.html", {
        **data,
        "reads_json": json.dumps(reads, ensure_ascii=False).replace("</", "<\\/"),
        "year": date.today().year,
    })


# ------------------------------------------------------------------ серии

@router.get("/series", response_class=HTMLResponse)
def series_list(request: Request):
    groups = {key: [] for key in ("in_progress", "to_read", "done", "abandoned")}
    for s in queries.series_list():
        groups[s["status"]].append(s)
    return templates.TemplateResponse(request, "series_list.html", {"groups": groups})


@router.get("/series/{series_id}", response_class=HTMLResponse)
def series_page(request: Request, series_id: int, error: str | None = None, edit: bool = False):
    s = queries.series_detail(series_id)
    if not s:
        raise HTTPException(404, "Серия не найдена")
    return templates.TemplateResponse(request, "series.html", {"s": s, "error": error, "edit": edit})


@router.post("/series/{series_id}")
async def series_save(request: Request, series_id: int):
    form = dict(await request.form())
    try:
        library.save_series(series_id, form)
    except library.ValidationError as e:
        return back(f"/series/{series_id}", str(e))
    return back(f"/series/{series_id}")


# ------------------------------------------------------------------ книга

@router.get("/book/{book_id}", response_class=HTMLResponse)
def book_page(request: Request, book_id: int, error: str | None = None):
    b = queries.book_detail(book_id)
    if not b:
        raise HTTPException(404, "Книга не найдена")
    return templates.TemplateResponse(request, "book.html", {
        "b": b, "genres": queries.genres(), "error": error, "today": date.today().isoformat()})


async def _book_action(request: Request, book_id: int, action) -> RedirectResponse:
    form = dict(await request.form())
    try:
        action(form)
    except library.ValidationError as e:
        return back(f"/book/{book_id}", str(e))
    return back(f"/book/{book_id}")


@router.post("/book/{book_id}")
async def book_save(request: Request, book_id: int):
    return await _book_action(request, book_id, lambda f: library.save_book(book_id, f))


@router.post("/book/{book_id}/add")
async def book_add(request: Request, book_id: int):
    return await _book_action(request, book_id, lambda f: library.add_to_library(book_id))


@router.post("/book/{book_id}/reads")
async def read_add(request: Request, book_id: int):
    return await _book_action(request, book_id, lambda f: library.add_read(book_id, f))


@router.post("/book/{book_id}/reads/{read_id}")
async def read_save(request: Request, book_id: int, read_id: int):
    return await _book_action(request, book_id, lambda f: library.save_read(book_id, read_id, f))


@router.post("/book/{book_id}/reads/{read_id}/delete")
async def read_delete(request: Request, book_id: int, read_id: int):
    return await _book_action(request, book_id, lambda f: library.delete_read(book_id, read_id))

"""Страницы приложения. Здесь только «какой адрес что показывает»:
данные берутся из services/queries.py, изменения — через services/library.py."""
import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape
from starlette.concurrency import run_in_threadpool

from services import catalog, covers, ficbook, hardcover_api, library, queries
from services.users import current_user_id

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
BOOKMARKLET = Path(__file__).parent.parent / "static" / "ficbook_bookmarklet.js"

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


def simple_md(text: str | None) -> Markup:
    """Описание из Notion: **жирный**, [ссылки](https://...) и строки «- пункт» -> HTML.
    Остальное — как текст (всё экранируется, поэтому HTML внутри описания не выполнится)."""
    out, items = [], []
    for line in (text or "").splitlines():
        html = str(escape(line.strip()))
        html = re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)",
                      r'<a href="\2" target="_blank" rel="noopener">\1</a>', html)
        html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
        html = html.replace("\\[", "[").replace("\\]", "]")
        if line.strip().startswith("- "):
            items.append(f"<li>{html[2:]}</li>")
            continue
        if items:
            out.append("<ul>" + "".join(items) + "</ul>")
            items = []
        if html:
            out.append(f"<p>{html}</p>")
    if items:
        out.append("<ul>" + "".join(items) + "</ul>")
    return Markup("".join(out))


templates.env.filters.update(ru_date=ru_date, stars=stars, position=position, md=simple_md)
templates.env.globals.update(STATUS=queries.STATUS_NAMES, SERIES_STATUS=queries.SERIES_STATUS_NAMES,
                             WORK_STATUS=queries.WORK_STATUS_NAMES)


def back(url: str, error: str | None = None) -> RedirectResponse:
    """После сохранения возвращаемся на страницу (303 — чтобы F5 не отправил форму повторно)."""
    return RedirectResponse(url + ("?" + urlencode({"error": error}) if error else ""), status_code=303)


# ------------------------------------------------------------------ главная

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    data = queries.home(current_user_id())
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
    for s in queries.series_list(current_user_id()):
        groups[s["status"]].append(s)
    return templates.TemplateResponse(request, "series_list.html", {"groups": groups})


@router.get("/series/{series_id}", response_class=HTMLResponse)
def series_page(request: Request, series_id: int, error: str | None = None, edit: bool = False):
    s = queries.series_detail(current_user_id(), series_id)
    if not s:
        raise HTTPException(404, "Серия не найдена")
    return templates.TemplateResponse(request, "series.html", {"s": s, "error": error, "edit": edit})


@router.post("/series/{series_id}")
async def series_save(request: Request, series_id: int):
    form = dict(await request.form())
    try:
        library.save_series(current_user_id(), series_id, form)
    except library.ValidationError as e:
        return back(f"/series/{series_id}", str(e))
    return back(f"/series/{series_id}")


# ------------------------------------------------------------------ книга

@router.post("/series/{series_id}/refresh")
async def series_refresh(series_id: int):
    try:
        await run_in_threadpool(catalog.refresh_series, series_id)
    except library.ValidationError as e:
        return back(f"/series/{series_id}", str(e))
    return back(f"/series/{series_id}")


# ------------------------------------------------------------------ добавить книгу

@router.get("/add/book", response_class=HTMLResponse)
def add_book_page(request: Request, q: str = "", error: str | None = None, link: int | None = None):
    """Поиск в Hardcover. Найденные книги, которые уже есть, помечены.
    link=<id книги> — поиск со страницы книги: результат не добавляется, а связывается с ней."""
    user_id = current_user_id()
    target = queries.book_detail(user_id, link) if link else None
    if link and not target:
        raise HTTPException(404, "Книга не найдена")
    results = []
    q = q.strip()
    if q:
        try:
            results = hardcover_api.search(q)
        except hardcover_api.HardcoverError as e:
            error = str(e)
        known = catalog.known(user_id, [r["id"] for r in results])
        for r in results:
            r["known"] = known.get(r["id"])
    return templates.TemplateResponse(request, "add_book.html",
                                      {"q": q, "results": results, "error": error, "target": target, "f": {}})


@router.post("/add/manual")
async def add_manual(request: Request):
    """Книга, которой нет в Hardcover."""
    form = dict(await request.form())
    try:
        book_id = catalog.add_manual(current_user_id(), form)
    except library.ValidationError as e:
        # без редиректа: иначе пропадёт всё, что ввела
        return templates.TemplateResponse(request, "add_book.html", {
            "q": "", "results": [], "error": str(e), "target": None, "f": form, "manual": True})
    return back(f"/book/{book_id}")


@router.post("/add/book")
async def add_book(request: Request):
    form = dict(await request.form())
    try:
        book_id = await run_in_threadpool(catalog.add_from_hardcover, current_user_id(), int(form["hardcover_id"]))
    except (KeyError, ValueError):
        return back("/add/book", "Не выбрана книга")
    except library.ValidationError as e:
        # возвращаемся к тем же результатам поиска
        return RedirectResponse("/add/book?" + urlencode({"q": form.get("q", ""), "error": str(e)}),
                                status_code=303)
    return back(f"/book/{book_id}")


@router.get("/book/{book_id}", response_class=HTMLResponse)
def book_page(request: Request, book_id: int, error: str | None = None):
    user_id = current_user_id()
    b = queries.book_detail(user_id, book_id)
    if not b:
        raise HTTPException(404, "Книга не найдена")
    return templates.TemplateResponse(request, "book.html", {
        "b": b, "genres": queries.genres(user_id), "error": error, "today": date.today().isoformat()})


async def _book_action(request: Request, book_id: int, action) -> RedirectResponse:
    form = dict(await request.form())
    try:
        action(form)
    except library.ValidationError as e:
        return back(f"/book/{book_id}", str(e))
    return back(f"/book/{book_id}")


@router.post("/book/{book_id}")
async def book_save(request: Request, book_id: int):
    return await _book_action(request, book_id, lambda f: library.save_book(current_user_id(), book_id, f))


@router.post("/book/{book_id}/add")
async def book_add(request: Request, book_id: int):
    return await _book_action(request, book_id, lambda f: library.add_to_library(current_user_id(), book_id))


@router.post("/book/{book_id}/reads")
async def read_add(request: Request, book_id: int):
    return await _book_action(request, book_id, lambda f: library.add_read(current_user_id(), book_id, f))


@router.post("/book/{book_id}/reads/{read_id}")
async def read_save(request: Request, book_id: int, read_id: int):
    return await _book_action(request, book_id, lambda f: library.save_read(current_user_id(), book_id, read_id, f))


@router.post("/book/{book_id}/refresh")
async def book_refresh(book_id: int):
    try:
        await run_in_threadpool(catalog.refresh_from_hardcover, book_id)
    except library.ValidationError as e:
        return back(f"/book/{book_id}", str(e))
    return back(f"/book/{book_id}")


@router.get("/book/{book_id}/covers", response_class=HTMLResponse)
def covers_page(request: Request, book_id: int):
    """Варианты обложки из Hardcover, Open Library, Google Books — выбрать одну."""
    b = queries.book_detail(current_user_id(), book_id)
    if not b:
        raise HTTPException(404, "Книга не найдена")
    found, failed = covers.candidates(b)
    return templates.TemplateResponse(request, "covers.html", {"b": b, "covers": found, "failed": failed})


@router.post("/book/{book_id}/cover")
async def cover_save(request: Request, book_id: int):
    form = dict(await request.form())
    try:
        library.set_cover(book_id, form.get("cover_url"))
    except library.ValidationError as e:
        return back(f"/book/{book_id}", str(e))
    return back(f"/book/{book_id}")


@router.post("/book/{book_id}/link")
async def book_link(request: Request, book_id: int):
    """Связать книгу (или фанфик) с найденной книгой Hardcover."""
    form = dict(await request.form())
    try:
        await run_in_threadpool(catalog.refresh_from_hardcover, book_id, int(form["hardcover_id"]))
    except (KeyError, ValueError):
        return back(f"/book/{book_id}", "Не выбрана книга")
    except library.ValidationError as e:
        return RedirectResponse("/add/book?" + urlencode({"q": form.get("q", ""), "link": book_id,
                                                           "error": str(e)}), status_code=303)
    return back(f"/book/{book_id}")


@router.get("/fanfics", response_class=HTMLResponse)
def fanfics_page(request: Request):
    groups = {key: [] for key in queries.STATUS_NAMES}
    for f in queries.fanfics(current_user_id()):
        groups[f["status"]].append(f)
    return templates.TemplateResponse(request, "fanfics.html", {"groups": groups})


def _ficbook_form(request: Request, form: dict | None = None, error: str | None = None):
    code = BOOKMARKLET.read_text(encoding="utf-8")
    code = "\n".join(line for line in code.splitlines() if not line.lstrip().startswith("//"))
    # APP_BASE_URL — внешний адрес приложения (Codespaces, хостинг): за прокси base_url бывает localhost
    base = os.getenv("APP_BASE_URL") or str(request.base_url)
    code = code.replace("__BASE__", base.rstrip("/"))
    return templates.TemplateResponse(request, "add_ficbook.html", {
        "f": form or {}, "error": error, "base": base.rstrip("/"),
        "bookmarklet": "javascript:" + quote(code, safe=""), "shortcut": code})


@router.get("/add/ficbook", response_class=HTMLResponse)
def ficbook_page(request: Request):
    """Форма фанфика. Закладка с ficbook открывает её с данными в адресе после # —
    форма заполняется сама; без закладки её можно заполнить вручную."""
    return _ficbook_form(request)


@router.post("/add/ficbook")
async def ficbook_save(request: Request):
    form = dict(await request.form())
    try:
        book_id = ficbook.save_fanfic(current_user_id(), form)
    except library.ValidationError as e:
        # без редиректа: иначе пропадёт всё, что прислала закладка
        return _ficbook_form(request, form, str(e))
    return back(f"/book/{book_id}")


@router.post("/book/{book_id}/reads/{read_id}/delete")
async def read_delete(request: Request, book_id: int, read_id: int):
    return await _book_action(request, book_id, lambda f: library.delete_read(current_user_id(), book_id, read_id))

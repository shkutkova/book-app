"""Точка входа: создаёт приложение и подключает страницы. Логика живёт в других файлах."""
from pathlib import Path
from urllib.parse import urlencode

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from psycopg import OperationalError
from psycopg_pool import PoolTimeout

load_dotenv()  # читает DATABASE_URL и HARDCOVER_TOKEN из .env до подключения страниц

from routes.pages import router as pages_router  # noqa: E402
from search import router as search_router  # noqa: E402
from services import auth  # noqa: E402

app = FastAPI(title="My Book App")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(pages_router)
app.include_router(search_router)


@app.middleware("http")
async def require_login(request: Request, call_next):
    """Все страницы — только после входа (кроме самой страницы входа и стилей)."""
    path = request.url.path
    if path.startswith(auth.OPEN_PATHS) or auth.is_logged_in(request.cookies.get(auth.COOKIE)):
        return await call_next(request)
    target = path + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse("/login?" + urlencode({"next": target}), status_code=303)


@app.exception_handler(PoolTimeout)
@app.exception_handler(OperationalError)
async def no_database(request: Request, exc: Exception):
    """Нет связи с базой — понятное сообщение вместо длинной ошибки."""
    return HTMLResponse(
        "<h1>Нет связи с базой</h1>"
        "<p>Приложение запущено, но не может подключиться к Supabase.</p>"
        "<p>Частая причина — сеть (рабочая или VPN) закрывает порты базы 5432 и 6543. "
        "Попробуй другую сеть, например раздачу с телефона, без VPN.</p>"
        "<p>Ещё проверь DATABASE_URL в .env: нужна строка Session pooler из Supabase.</p>",
        status_code=503)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

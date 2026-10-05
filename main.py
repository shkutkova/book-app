"""Точка входа: создаёт приложение и подключает страницы. Логика живёт в других файлах."""
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()  # читает DATABASE_URL и HARDCOVER_TOKEN из .env до подключения страниц

from routes.pages import router as pages_router  # noqa: E402
from search import router as search_router  # noqa: E402

app = FastAPI(title="My Book App")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(pages_router)
app.include_router(search_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

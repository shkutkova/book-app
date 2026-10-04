"""Точка входа: создаёт приложение и подключает страницы. Логика живёт в других файлах."""
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()  # читает токен из .env до подключения страниц

from dashboard import router as dashboard_router  # noqa: E402
from search import router as search_router  # noqa: E402
from series import router as series_router  # noqa: E402

app = FastAPI(title="My Book App")
app.include_router(dashboard_router)
app.include_router(search_router)
app.include_router(series_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
"""Кто сейчас пользуется приложением.
Входа пока нет: берётся APP_USER_ID из .env, а если его нет — единственный профиль в базе.
Когда появится вход, здесь будет пользователь из сессии, остальной код не изменится."""
import os
from functools import cache

from db import fetch_all


@cache
def current_user_id() -> str:
    if os.getenv("APP_USER_ID"):
        return os.environ["APP_USER_ID"]
    rows = fetch_all("select id from profiles limit 2")
    if len(rows) != 1:
        raise RuntimeError(
            "Не понятно, чьи книги показывать: в таблице profiles "
            f"{'нет записей' if not rows else 'несколько записей'}. Укажи APP_USER_ID в .env")
    return str(rows[0]["id"])

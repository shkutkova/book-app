"""Вход по паролю — пока пользователь один.
Пароль — APP_PASSWORD в .env / настройках хостинга. Если он не задан, вход выключен
(удобно локально), а на страницах висит предупреждение.

После входа браузер получает cookie «до какого времени пускать + подпись». Подпись — HMAC
от пароля (и SESSION_SECRET, если задан): подделать cookie, не зная пароля, нельзя,
а смена пароля разлогинивает все устройства."""
import hashlib
import hmac
import os
import time

COOKIE = "session"
MAX_AGE = 365 * 24 * 3600  # на телефоне не хочется вводить пароль часто
# Без входа доступны только страница входа и статика (стили)
OPEN_PATHS = ("/login", "/static/")


def password() -> str | None:
    return os.getenv("APP_PASSWORD") or None


def _sign(value: str) -> str:
    key = ((os.getenv("SESSION_SECRET") or "") + (password() or "")).encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def check_password(given: str | None) -> bool:
    expected = password()
    return bool(expected and given) and hmac.compare_digest(given.encode(), expected.encode())


def new_cookie() -> str:
    until = str(int(time.time()) + MAX_AGE)
    return f"{until}.{_sign(until)}"


def is_logged_in(cookie: str | None) -> bool:
    if not password():
        return True
    until, _, sig = (cookie or "").partition(".")
    return (until.isdigit() and int(until) > time.time()
            and hmac.compare_digest(sig, _sign(until)))


def safe_next(url: str | None) -> str:
    """Куда вернуться после входа — только адрес внутри приложения."""
    return url if url and url.startswith("/") and not url.startswith("//") else "/"

"""«Отправить на Kindle»: письмо с epub на адрес @kindle.com от своего Gmail — через Gmail API (https).
Обычная почта (SMTP) с бесплатного Render не уходит: порты 25/465/587 закрыты с сентября 2025.

Нужно в .env (и в Render → Environment):
- GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET — OAuth-клиент «Desktop app» из Google Cloud;
- GMAIL_REFRESH_TOKEN — один раз получить: .venv/Scripts/python.exe scripts/gmail_token.py (сам допишет в .env);
- KINDLE_EMAIL — адрес Kindle (Amazon → Content & Devices → Devices → «Send-to-Kindle E-mail»).
Свой Gmail должен быть в списке одобренных отправителей Amazon (Preferences → Personal Document Settings)."""
import os
from email.message import EmailMessage

import httpx

KEYS = ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN", "KINDLE_EMAIL")
SEND_URL = "https://gmail.googleapis.com/upload/gmail/v1/users/me/messages/send?uploadType=media"


class KindleError(Exception):
    """Понятное сообщение: что не так с отправкой."""


def enabled() -> bool:
    return all(os.getenv(k) for k in KEYS)


def _access_token() -> str:
    """Долгий ключ (refresh token) -> короткий (на час) для запроса к Gmail."""
    try:
        r = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
            "client_id": os.getenv("GMAIL_CLIENT_ID"), "client_secret": os.getenv("GMAIL_CLIENT_SECRET"),
            "refresh_token": os.getenv("GMAIL_REFRESH_TOKEN"), "grant_type": "refresh_token"})
    except httpx.HTTPError:
        raise KindleError("Не получилось связаться с Google — попробуй ещё раз")
    if r.status_code != 200:
        # invalid_grant — ключ отозван или истёк (приложение в Google Cloud осталось в режиме «Testing»)
        raise KindleError("Google не пустил к почте: ключ устарел. Получи новый — scripts/gmail_token.py")
    return r.json()["access_token"]


def message(data: bytes, filename: str, title: str) -> bytes:
    """Письмо на Kindle: тема — название, во вложении epub."""
    msg = EmailMessage()
    msg["To"] = os.getenv("KINDLE_EMAIL")
    msg["Subject"] = title or filename
    msg.set_content("Отправлено из Spooky Book Universe.")
    msg.add_attachment(data, maintype="application", subtype="epub+zip", filename=filename)
    return msg.as_bytes()


def send(data: bytes, filename: str, title: str = "") -> str:
    """Отправляет epub на Kindle. Возвращает адрес, куда ушло."""
    if not enabled():
        raise KindleError("Отправка на Kindle не настроена: нет ключей Gmail или адреса Kindle")
    if len(data) > 35 * 1024 * 1024:
        raise KindleError("Файл больше 35 МБ — Gmail такой не отправит")
    try:
        r = httpx.post(SEND_URL, timeout=90, content=message(data, filename, title),
                       headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "message/rfc822"})
    except httpx.HTTPError:
        raise KindleError("Не получилось отправить — нет связи с Gmail, попробуй ещё раз")
    if r.status_code == 403:
        raise KindleError("Gmail отказал: у ключа нет права отправлять почту — получи ключ заново (scripts/gmail_token.py)")
    if r.status_code >= 300:
        raise KindleError(f"Gmail не отправил письмо (ошибка {r.status_code})")
    return os.getenv("KINDLE_EMAIL")

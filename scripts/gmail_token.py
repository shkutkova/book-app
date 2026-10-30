"""Один раз: получить ключ Gmail для «Отправить на Kindle» (GMAIL_REFRESH_TOKEN) и записать его в .env.
Перед запуском в .env должны быть GMAIL_CLIENT_ID и GMAIL_CLIENT_SECRET (OAuth-клиент «Desktop app»).
Запуск из корня проекта: .venv/Scripts/python.exe scripts/gmail_token.py
Откроется браузер: войти в свой Gmail → разрешить «Отправлять письма». Ключ в консоль не выводится."""
import http.server
import os
import re
import secrets
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows иначе показывает кракозябры
sys.stderr.reconfigure(encoding="utf-8")
ENV = Path(__file__).resolve().parent.parent / ".env"
SCOPE = "https://www.googleapis.com/auth/gmail.send"  # только отправка: читать почту сайт не может
load_dotenv(ENV)
client_id, client_secret = os.getenv("GMAIL_CLIENT_ID"), os.getenv("GMAIL_CLIENT_SECRET")
if not client_id or not client_secret:
    sys.exit("В .env нет GMAIL_CLIENT_ID и GMAIL_CLIENT_SECRET — сначала создай OAuth-клиент в Google Cloud.")

state, result = secrets.token_urlsafe(16), {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # Google возвращает сюда ?code=…
        q = parse_qs(urlparse(self.path).query)
        if q.get("state", [""])[0] == state:
            result["code"] = q.get("code", [""])[0]
            result["error"] = q.get("error", [""])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("Готово — можно закрыть вкладку и вернуться в консоль.".encode())

    def log_message(self, *args):
        pass


server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
redirect = f"http://127.0.0.1:{server.server_port}"
url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
    "client_id": client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
    "access_type": "offline", "prompt": "consent", "state": state})
threading.Thread(target=server.handle_request, daemon=True).start()
print("Открываю браузер. Если не открылся — скопируй ссылку:\n" + url)
webbrowser.open(url)
while "code" not in result:
    threading.Event().wait(0.5)
server.server_close()
if not result.get("code"):
    sys.exit(f"Google не дал разрешение: {result.get('error') or 'нет кода'}")

r = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
    "code": result["code"], "client_id": client_id, "client_secret": client_secret,
    "redirect_uri": redirect, "grant_type": "authorization_code"})
token = r.json().get("refresh_token") if r.status_code == 200 else None
if not token:
    sys.exit(f"Не получилось получить ключ (ответ Google {r.status_code}). Попробуй ещё раз.")

text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
line = f"GMAIL_REFRESH_TOKEN={token}"
text = re.sub(r"(?m)^GMAIL_REFRESH_TOKEN=.*$", line, text) if "GMAIL_REFRESH_TOKEN=" in text \
    else text.rstrip("\n") + ("\n" if text else "") + line + "\n"
ENV.write_text(text, encoding="utf-8")
print("Ключ записан в .env (GMAIL_REFRESH_TOKEN). Для сайта на Render скопируй его оттуда в Environment.")

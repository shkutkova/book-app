"""ИИ для «Подробнее» — увлекательное описание без спойлеров.
- «Спросить Google ИИ»: ссылка в режим ИИ Google с готовым запросом (ask_url) — бесплатно, без ключа;
  ответ копируешь в поле сама.
- «Написать с ИИ»: Gemini с поиском Google прямо с сервера — только если задан GEMINI_API_KEY
  (aistudio.google.com; из России ключ не создать — аккаунт с российской страной не пускают).
Текст не сохраняется сам — его проверяют."""
import os
from urllib.parse import quote

import httpx

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = "gemini-2.5-flash"
GOOGLE_AI = "https://www.google.com/search?udm=50&q="  # udm=50 — режим ИИ

ASK = ("Напиши аннотацию к {what} «{title}»{orig}{authors}{fandoms}{link}. "
       "Увлекательно расскажи про сюжет, но без спойлеров, и подсвети особые плюсы: атмосфера, герои, их динамика, стиль. "
       "Формат: 2–3 абзаца, затем 3–5 пунктов «Плюс: пояснение». Без ссылок и сносок.")

FULL = ASK + """
Сначала найди {what_acc} в интернете. Если надёжных сведений не нашлось — опирайся только на данные ниже и ничего не выдумывай.

Что известно:
{facts}

Пункты оформи списком вида «- **Плюс:** пояснение». Без заголовков и вступлений вроде «Вот аннотация». На русском."""


class AIError(RuntimeError):
    """ИИ не ответил или ответил ошибкой — текст показывается рядом с кнопкой."""


def enabled() -> bool:
    return bool(os.getenv("GEMINI_API_KEY"))


def _fields(b: dict) -> dict:
    fanfic = b.get("kind") == "fanfic"
    return dict(
        what="фанфику" if fanfic else "книге", what_acc="фанфик" if fanfic else "книгу",
        title=b.get("title_ru") or b["title"],
        orig=f" (в оригинале «{b['title']}»)" if b.get("title_ru") else "",
        authors=f", автор: {b['authors']}" if b.get("authors") else "",
        fandoms=f", фандом: {', '.join(b['fandoms'])}" if b.get("fandoms") else "",
        # ссылка на ficbook помогает найти именно этот фанфик
        link=f", {b['source_url']}" if b.get("source_url") else "")


def ask_url(b: dict) -> str:
    """Ссылка «Спросить Google ИИ»: запрос короткий — длинный адрес Google обрезает."""
    return GOOGLE_AI + quote(ASK.format(**_fields(b)))


def write_description(b: dict) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise AIError("Не задан GEMINI_API_KEY в .env и в Environment на Render")
    tags = b.get("hardcover_tags") or {}
    meta = b.get("ficbook_meta") or {}
    labels = (tags.get("genres") or []) + (meta.get("tags") or [])
    annot = b.get("description_ru") or b.get("description")
    facts = [f"Аннотация: {annot}" if annot else None,
             f"Метки: {', '.join(dict.fromkeys(labels))}" if labels else None,
             f"Направление: {meta['direction']}" if meta.get("direction") else None]
    text = FULL.format(**_fields(b), facts="\n".join(f for f in facts if f) or "ничего, кроме названия и автора")
    try:
        r = httpx.post(GEMINI_URL.format(model=os.getenv("GEMINI_MODEL") or GEMINI_MODEL), timeout=90,
                       json={"contents": [{"parts": [{"text": text}]}], "tools": [{"google_search": {}}]},
                       headers={"x-goog-api-key": key})
    except httpx.HTTPError as e:
        raise AIError(f"Gemini не отвечает: {e}")
    if r.status_code == 429:
        raise AIError("Лимит бесплатных запросов к Gemini — попробуй позже")
    if r.status_code != 200:
        msg = (r.json().get("error") or {}).get("message", "") if "json" in r.headers.get("content-type", "") else ""
        raise AIError(f"Gemini ответил ошибкой {r.status_code}. {msg}".strip())
    parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    out = "".join(p.get("text", "") for p in parts).strip()
    if not out:
        raise AIError("Gemini вернул пустой ответ — попробуй ещё раз")
    return out

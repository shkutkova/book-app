"""Gemini (Google): черновик «Подробнее» — увлекательное описание без спойлеров.
Ключ — GEMINI_API_KEY из .env (aistudio.google.com, бесплатный уровень); модель — GEMINI_MODEL.
Gemini сначала ищет книгу в Google (google_search), иначе про фанфики он выдумывает.
Запросы идут только с сервера: в браузер ключ не попадает. Текст не сохраняется сам — его проверяют."""
import os

import httpx

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODEL = "gemini-2.5-flash"

PROMPT = """Напиши аннотацию к {what} «{title}»{orig}{authors}{fandoms}.
Увлекательно расскажи про сюжет, но без спойлеров, и подсвети особые плюсы: атмосфера, герои, их динамика, стиль.
Сначала найди {what_acc} в интернете{where}. Если надёжных сведений не нашлось — опирайся только на данные ниже и ничего не выдумывай.

Что известно:
{facts}

Формат: 2–3 абзаца связного текста, затем 3–5 пунктов списком, каждый вида «- **Плюс:** пояснение».
Без заголовков, без вступлений вроде «Вот аннотация», без ссылок и сносок. На русском."""


class GeminiError(RuntimeError):
    """Gemini не ответил или ответил ошибкой — текст показывается рядом с кнопкой."""


def prompt(b: dict) -> str:
    fanfic = b.get("kind") == "fanfic"
    tags = b.get("hardcover_tags") or {}
    meta = b.get("ficbook_meta") or {}
    labels = (tags.get("genres") or []) + (meta.get("tags") or [])
    facts = [f"Аннотация: {b.get('description_ru') or b.get('description')}" if (b.get("description_ru") or b.get("description")) else None,
             f"Метки: {', '.join(dict.fromkeys(labels))}" if labels else None,
             f"Направление: {meta['direction']}" if meta.get("direction") else None,
             f"Рейтинг: {meta['rating']}" if meta.get("rating") else None,
             f"Ссылка: {b['source_url']}" if b.get("source_url") else None]
    return PROMPT.format(
        what="фанфику" if fanfic else "книге", what_acc="фанфик" if fanfic else "книгу",
        title=b.get("title_ru") or b["title"],
        orig=f" (в оригинале «{b['title']}»)" if b.get("title_ru") else "",
        authors=f", автор: {b['authors']}" if b.get("authors") else "",
        fandoms=f", фандом: {', '.join(b['fandoms'])}" if b.get("fandoms") else "",
        where=" (ficbook.net, AO3, отзывы читателей)" if fanfic else " (Goodreads, LiveLib, отзывы читателей)",
        facts="\n".join(f for f in facts if f) or "ничего, кроме названия и автора")


def write_description(b: dict) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise GeminiError("Не задан GEMINI_API_KEY в .env (и в Environment на Render)")
    body = {"contents": [{"parts": [{"text": prompt(b)}]}], "tools": [{"google_search": {}}]}
    try:
        r = httpx.post(URL.format(model=os.getenv("GEMINI_MODEL") or MODEL), json=body, timeout=90,
                       headers={"x-goog-api-key": key})
    except httpx.HTTPError as e:
        raise GeminiError(f"Gemini не отвечает: {e}")
    if r.status_code == 429:
        raise GeminiError("Лимит бесплатных запросов к Gemini — попробуй позже")
    if r.status_code != 200:
        msg = (r.json().get("error") or {}).get("message", "") if "json" in r.headers.get("content-type", "") else ""
        raise GeminiError(f"Gemini ответил ошибкой {r.status_code}. {msg}".strip())
    parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise GeminiError("Gemini вернул пустой ответ — попробуй ещё раз")
    return text

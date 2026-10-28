"""ИИ: черновик «Подробнее» — увлекательное описание без спойлеров.
OPENROUTER_API_KEY (openrouter.ai, бесплатные модели; модели — OPENROUTER_MODEL через запятую, первая основная)
или GEMINI_API_KEY (aistudio.google.com; модель — GEMINI_MODEL). Задан OpenRouter — берётся он.
Gemini сначала ищет книгу в Google; бесплатные модели OpenRouter интернета не видят — пишут только по нашим данным.
Запросы идут только с сервера: в браузер ключ не попадает. Текст не сохраняется сам — его проверяют."""
import os

import httpx

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = "gemini-2.5-flash"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# бесплатные (:free) меняются — актуальные: openrouter.ai/models?max_price=0
OPENROUTER_MODELS = "thinkingmachines/inkling:free,nvidia/nemotron-3-ultra-550b-a55b:free"

PROMPT = """Напиши аннотацию к {what} «{title}»{orig}{authors}{fandoms}.
Увлекательно расскажи про сюжет, но без спойлеров, и подсвети особые плюсы: атмосфера, герои, их динамика, стиль.
{source}

Что известно:
{facts}

Формат: 2–3 абзаца связного текста, затем 3–5 пунктов списком, каждый вида «- **Плюс:** пояснение».
Без заголовков, без вступлений вроде «Вот аннотация», без ссылок и сносок. На русском."""

SEARCH = ("Сначала найди {what_acc} в интернете{where}. "
          "Если надёжных сведений не нашлось — опирайся только на данные ниже и ничего не выдумывай.")
NO_SEARCH = ("Интернета у тебя нет: опирайся только на данные ниже. Не придумывай событий, имён и поворотов, "
             "которых там нет, — лучше раскрой настроение, конфликт и обещание истории. Данных мало — пиши короче.")


class AIError(RuntimeError):
    """ИИ не ответил или ответил ошибкой — текст показывается рядом с кнопкой."""


def prompt(b: dict, search: bool = True) -> str:
    fanfic = b.get("kind") == "fanfic"
    tags = b.get("hardcover_tags") or {}
    meta = b.get("ficbook_meta") or {}
    labels = (tags.get("genres") or []) + (meta.get("tags") or [])
    annot = b.get("description_ru") or b.get("description")
    facts = [f"Аннотация: {annot}" if annot else None,
             f"Метки: {', '.join(dict.fromkeys(labels))}" if labels else None,
             f"Настроение: {', '.join(tags['moods'])}" if tags.get("moods") else None,
             f"Направление: {meta['direction']}" if meta.get("direction") else None,
             f"Рейтинг: {meta['rating']}" if meta.get("rating") else None,
             f"Ссылка: {b['source_url']}" if search and b.get("source_url") else None]
    what, what_acc = ("фанфику", "фанфик") if fanfic else ("книге", "книгу")
    where = " (ficbook.net, AO3, отзывы читателей)" if fanfic else " (Goodreads, LiveLib, отзывы читателей)"
    return PROMPT.format(
        what=what, title=b.get("title_ru") or b["title"],
        orig=f" (в оригинале «{b['title']}»)" if b.get("title_ru") else "",
        authors=f", автор: {b['authors']}" if b.get("authors") else "",
        fandoms=f", фандом: {', '.join(b['fandoms'])}" if b.get("fandoms") else "",
        source=SEARCH.format(what_acc=what_acc, where=where) if search else NO_SEARCH,
        facts="\n".join(f for f in facts if f) or "ничего, кроме названия и автора")


def write_description(b: dict) -> str:
    if os.getenv("OPENROUTER_API_KEY"):
        return _openrouter(prompt(b, search=False))
    if os.getenv("GEMINI_API_KEY"):
        return _gemini(prompt(b))
    raise AIError("Не задан ключ ИИ: OPENROUTER_API_KEY (или GEMINI_API_KEY) в .env и в Environment на Render")


def _post(name: str, url: str, body: dict, headers: dict) -> dict:
    try:
        r = httpx.post(url, json=body, timeout=90, headers=headers)
    except httpx.HTTPError as e:
        raise AIError(f"{name} не отвечает: {e}")
    if r.status_code == 429:
        raise AIError(f"Лимит бесплатных запросов к {name} — попробуй позже")
    if r.status_code != 200:
        msg = (r.json().get("error") or {}).get("message", "") if "json" in r.headers.get("content-type", "") else ""
        raise AIError(f"{name} ответил ошибкой {r.status_code}. {msg}".strip())
    return r.json()


def _text(text: str | None) -> str:
    if not (text or "").strip():
        raise AIError("ИИ вернул пустой ответ — попробуй ещё раз")
    return text.strip()


def _openrouter(text: str) -> str:
    models = [m.strip() for m in (os.getenv("OPENROUTER_MODEL") or OPENROUTER_MODELS).split(",") if m.strip()]
    # models — запасные: основная занята или пропала из бесплатных, OpenRouter берёт следующую
    data = _post("OpenRouter", OPENROUTER_URL,
                 {"models": models, "messages": [{"role": "user", "content": text}], "reasoning": {"exclude": True}},
                 {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}", "X-Title": "Book app"})
    if data.get("error"):
        raise AIError(f"OpenRouter: {data['error'].get('message')}")
    return _text(((data.get("choices") or [{}])[0].get("message") or {}).get("content"))


def _gemini(text: str) -> str:
    data = _post("Gemini", GEMINI_URL.format(model=os.getenv("GEMINI_MODEL") or GEMINI_MODEL),
                 {"contents": [{"parts": [{"text": text}]}], "tools": [{"google_search": {}}]},
                 {"x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return _text("".join(p.get("text", "") for p in parts))

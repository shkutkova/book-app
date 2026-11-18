"""Страницы на выдуманных данных — без базы (с рабочей сети к Supabase не подключиться).
Подменяет функции services.queries и изменения в services.library, сервер на http://127.0.0.1:8011.
Запуск из корня проекта: .venv/Scripts/python.exe scripts/dev_fake.py
Вход выключен (APP_PASSWORD пустой). Если в queries появились новые поля — дописать их сюда."""
import os, random, sys
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["APP_PASSWORD"] = ""; os.environ["APP_USER_ID"] = "fake"
from services import queries
random.seed(3)
G = ["Dark Romance", "Fantasy", "Romance", "Fan Fiction", "Dark Fantasy", "Mafia Romance", "Urban Fantasy", None]
A = ["Rina Kent", "Ilona Andrews", "Leigh Rivers", "Evie Marceau", "Kate Stewart", "J. Bree", "Sarah J. Maas"]
rows = []
for i in range(136):
    d = date(2026, 3, 1) + timedelta(days=random.randint(0, 235))
    rows.append({"finished_at": d, "id": i % 120, "title": f"Книга номер {i}", "cover_url": None,
                 "pages": random.choice([0, 150, 280, 350, 390, 420, 480, 520, 580, 700, 1100]),
                 "rating": random.choice([None, 3, 4, 4.5, 5, 5, 5]), "genre": random.choice(G),
                 "authors": random.choice(A)})
rows.append({"finished_at": None, "id": 500, "title": "Без даты", "cover_url": None, "pages": 300,
             "rating": 5, "genre": "Fantasy", "authors": "Rina Kent"})
rows.append({"finished_at": date(2025, 11, 3), "id": 501, "title": "Прошлый год", "cover_url": None, "pages": 300,
             "rating": 4, "genre": "Romance", "authors": "Kate Stewart"})
rows.sort(key=lambda r: (r["finished_at"] is not None, r["finished_at"] or date.min))
queries.stats = lambda u: rows
COV = "https://assets.hardcover.app/edition/31173970/920e9d065f6a8cd28ac63e6b326607da89bea878.jpeg"
def B(i, st, kind="book", cov=None, **k):
    d = {"id": i, "kind": kind, "title": f"The Serpent and the Wings of Night {i}" if i % 3 else f"Книга {i}", "title_ru": None,
         "cover_url": cov, "pages": 300 + i, "status": st, "rating": [None, 4, 4.5, 5][i % 4], "is_favorite": False,
         "authors": ["Rina Kent", "Carissa Broadbent", "SenLinYu"][i % 3], "series": None, "finished_at": date(2026, 10, i % 27 + 1) if st == "finished" else None,
         "work_status": None, "annot": "Для людей и вампиров правила выживания одинаковы: никогда не доверяй, никогда не уступай и всегда — всегда — оберегай своё сердце.\nПриёмная дочь короля вампиров Орайя всю жизнь провела в золотой клетке." if i % 5 else None,
         "my_description": "Спустя десять лет после окончания войны в волшебном мире назревает скандал. В Британии орудует сеть контрабандистов, торгующая артефактами и порталами.\n- **Медленное сближение** героев\n- **Детективная интрига** до последней главы" if i % 3 == 0 else None}
    d.update(k); return d
queries.home = lambda u: {"counts": {"finished": 136}, "reading": [
        B(1, "reading", cov=COV, series={"name": "Crowns of Nyaxia", "pos": 1, "total": 3}),
        B(2, "reading", kind="fanfic"), B(3, "reading", cov=COV, series={"name": "Deception", "pos": 2, "total": 3})],
    "board": {"year_reads": 136, "month_reads": 11, "year_fanfics": 51, "year_pages": 64957, "month_pages": 5120, "series_done": 22,
              "best_month": {"month": 9, "n": 26}},
    "series": [{"id": 3, "name": "Crowns of Nyaxia", "name_ru": None, "total_books": 3, "finished_books": 0, "is_reading": True,
                "authors": "Carissa Broadbent", "statuses": ["reading", "want_to_read", "want_to_read"]},
               {"id": 4, "name": "Legacy of Gods", "name_ru": None, "total_books": 6, "finished_books": 5, "is_reading": False,
                "authors": "Rina Kent", "statuses": ["finished"] * 5 + ["want_to_read"]},
               {"id": 5, "name": "Blood and Ash", "name_ru": "Кровь и пепел", "total_books": 10, "finished_books": 3, "is_reading": False,
                "authors": "Jennifer L. Armentrout", "statuses": ["finished"] * 3 + ["want_to_read"] * 7}]}
queries.books = lambda u: [B(i, st, cov=COV if i % 2 else None, series="Crowns of Nyaxia · 1" if i % 4 == 0 else None)
                           for i, st in enumerate(["reading"] * 2 + ["want_to_read"] * 30 + ["finished"] * 40 + ["paused", "dnf"])]
queries.fanfics = lambda u: [B(100 + i, st, kind="fanfic", is_favorite=i % 6 == 1) for i, st in enumerate(["reading"] + ["want_to_read"] * 12 + ["finished"] * 9)]

# ---- страница книги, серии, обложки, полка
from services import covers as _covers
_home = queries.home
def _home2(u):
    h = _home(u)
    for s in h["series"]:
        s["books"] = [{"id": 10 + i, "title": f"Книга {i}", "cover_url": COV if i % 2 == 0 else None, "status": st}
                      for i, st in enumerate(s.pop("statuses"))]
    return h
queries.home = _home2
queries.genres = lambda u: [{"id": 1, "name": "Fantasy", "color": None}, {"id": 2, "name": "Dark Romance", "color": None}]
def _book(u, bid):
    b = B(bid, "finished" if bid % 2 else "reading", cov=COV if bid != 27 else None,
          kind="fanfic" if bid == 27 else "book")
    b.update({"title_ru": "Змея и крылья ночи" if bid == 6 else None, "description": "Для людей и вампиров правила выживания одинаковы: никогда не доверяй, никогда не уступай и всегда — всегда — оберегай своё сердце.\n\nПриёмная дочь короля вампиров...",
              "description_ru": None, "release_date": date(2022, 3, 1), "source_url": "https://ficbook.net/readfic/1" if bid == 27 else None,
              "hardcover_id": 1, "hardcover_slug": "the-serpent" if bid != 27 else None,
              "hardcover_tags": {"genres": ["Fantasy", "Romance", "Romantasy", "Vampires"], "moods": ["dark", "Adventurous", "tense", "emotional", "funny"],
                                 "content_warnings": ["Violence"]},
              "fandoms": ["Гарри Поттер"] if bid == 27 else None,
              "work_status": "finished" if bid == 27 else None, "words": 120000 if bid == 27 else None, "parts": 30 if bid == 27 else None,
              "ficbook_meta": {"direction": "Гет", "rating": "NC-17", "tags": ["Слоуберн", "Hurt/Comfort"]} if bid == 27 else None,
              "in_library": True, "my_genre_id": 1, "notes": "", "my_description": "Спустя десять лет после окончания войны в волшебном мире назревает скандал. В Британии орудует сеть контрабандистов, торгующая артефактами и порталами.\n\nГлавной неожиданностью становится приказ «сверху»: включить в группу Драко Малфоя.\n\nНикто не знает, где он пропадал десять лет. Его досье запечатано, доступ запрещён даже Поттеру. Малфой возвращается изменившимся — спокойным, уверенным профессионалом.\n\nИ чем глубже они продвигаются в деле, тем очевиднее: самые охраняемые тайны Министерства меркнут перед напряжением между бывшими врагами.\n\n**Почему это стоит прочитать?**\n- **Медленное развитие (Slow-burn):** Сюжет не бросает героев в объятия друг друга с первой главы. Отношения развиваются последовательно — от старой ненависти через вынужденное партнёрство к глубокой зависимости.\n- **Детективная интрига:** Расследование держит до последней главы, улики раскладываются честно, и разгадку можно найти самой.\n- **Повзрослевшие герои:** Взгляд на персонажей спустя десять лет после войны: у каждого своя внутренняя драма и своя цена победы." if bid == 27 else None, "is_favorite": bid == 6,
              "series": [] if bid == 27 else [{"id": 3, "name": "Crowns of Nyaxia", "name_ru": None, "sort_position": 1, "books_count": 3}],
              "reads": [{"id": 1, "started_at": date(2026, 10, 1), "finished_at": date(2026, 10, 9) if bid % 2 else None}]})
    return b
queries.book_detail = _book
_covers.candidates = lambda b: ([{"url": COV + "?v=2", "source": "Hardcover", "label": "Другое издание"}], ["Google Books"])
queries.series_list = lambda u: [{"id": i, "name": n, "name_ru": None, "authors": "Rina Kent", "status": st,
                                  "finished_books": f, "total_books": t, "is_reading": st == "in_progress" and i == 1,
                                  "books": [{"id": 30 + j, "title": f"B{j}", "title_ru": None, "cover_url": COV if j % 2 == 0 else None,
                                             "status": "finished" if j < f else "want_to_read"} for j in range(t)]}
                                 for i, (n, st, f, t) in enumerate([("Crowns of Nyaxia", "in_progress", 0, 3), ("Legacy of Gods", "done", 6, 6),
                                                                    ("Blood and Ash", "to_read", 0, 10), ("Throne of Glass", "to_read", 0, 7)])]
_home3 = queries.home
def _home4(u):
    h = _home3(u)
    C = ["https://assets.hardcover.app/edition/31173970/920e9d065f6a8cd28ac63e6b326607da89bea878.jpeg", None,
         "https://assets.hardcover.app/edition/30387367/8cb5e1af2d0bbbb3ff0a1b5ac7e0c9b4d2f8f8b2.jpeg"]
    k = lambda b: dict(b, key=f"b{b['id']}")
    h["shelf"] = {"fav": [k(B(200 + i, "finished", cov=COV if i % 2 else None, is_favorite=True)) for i in range(9)],
                  "reading": [k(B(1, "reading", cov=COV)), k(B(2, "reading", kind="fanfic"))],
                  "want": [k(B(300 + i, "want_to_read", is_next=True, cov=COV if i != 1 else None)) for i in range(5)]}
    if HOME_MODE[0] in ("empty", "nonext"):  # /fake/home/… — проверить заглушку «ничего не читаю»
        h["reading"] = []
    if HOME_MODE[0] == "nonext":
        h["shelf"] = dict(h["shelf"], want=[])
    return h
HOME_MODE = ["normal"]
queries.home = _home4
EXTRA = {50: True}  # книга -> в «Дополнительно» (перенос кнопкой меняет это)
def _series(u, sid):
    books = [dict(B(40 + i, st, cov=COV if i % 2 == 0 else None), official_position=i + 1, my_position=None, sort_position=i + 1)
             for i, st in enumerate(["finished", "finished", "reading", "want_to_read"])]
    books.append(dict(B(50, None), official_position=1.5, my_position=None, sort_position=1.5))
    for b in books:
        b["is_main"] = not EXTRA.get(b["id"], False)
    books.sort(key=lambda b: b["sort_position"])
    return {"id": sid, "name": "Crowns of Nyaxia", "name_ru": "Короны Никсии", "description": "Тёмное романтическое фэнтези о вампирах и богах.\nСерия рассказывает о мире Никсии, где правят дома Ночи, Тени и Крови. Каждая книга — новая пара героев, но мир и интриги общие, и с каждой книгой всё сложнее понять, кому верить.\nВ серии **основные книги** и повести.\n- Книга 1 — Змея и крылья ночи\n- Книга 2 — Пепел и проклятый звёздами король",
            "ficbook_id": None, "hardcover_id": 1, "is_completed": False, "is_abandoned": False, "use_my_order": False,
            "is_favorite": sid == 3, "total_books": 4, "finished_books": 2, "skipped_books": 0, "extra_books": 1,
            "progress_status": "in_progress", "books": [b for b in books if b["is_main"]], "extras": [b for b in books if not b["is_main"]],
            "authors": ["Carissa Broadbent"], "pages": 2100}
queries.series_detail = _series
_sl = queries.series_list
queries.series_list = lambda u: [dict(x, is_favorite=x["id"] == 1) for x in _sl(u)]

queries.find_books = lambda u, q: [dict(B(6, "finished", cov=COV), title_ru="Змея и крылья ночи", series="Crowns of Nyaxia · 1", in_library=True)]

from services import library as _lib
_lib.save_shelf_order = lambda u, shelf, items: print("SHELF", shelf, items)

NEXTS = {8: True}  # «Следующая» — до перезапуска
_lib.set_next = lambda u, b, on: NEXTS.__setitem__(b, on)
_bk = queries.book_detail
queries.book_detail = lambda u, bid: dict(_bk(u, bid), status="want_to_read", is_next=NEXTS.get(bid, False)) if bid in (8, 10) else _bk(u, bid)
_b2 = queries.books
queries.books = lambda u: [dict(b, is_next=b["status"] == "want_to_read" and b["id"] % 5 == 0, is_favorite=b["id"] % 7 == 2,
                                title_ru="Змея и крылья ночи" if b["id"] % 3 == 1 else None) for b in _b2(u)]
_lib.save_tags = lambda b, f: print("TAGS", b, dict(f))
_lib.delete_book = lambda u, b: (print("DELETE", b), "fanfic")[1]
_lib.set_series_extra = lambda u, s, b, extra: EXTRA.__setitem__(b, extra)
_lib.remove_from_series = lambda s, b: print("REMOVE", s, b)
_lib.delete_series = lambda s: print("DELETE SERIES", s)
queries.series_names = lambda: ["Crowns of Nyaxia", "Короны Никсии", "Deception", "Пространство между мирами"]
from services import catalog as _cat
_cat.add_to_series = lambda b, name, pos: print("TO SERIES", b, name, pos)
_lib.set_cover = lambda b, url: print("COVER", b, _lib.cover_link(url))
FILES = {6: "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view?usp=sharing",
         8: "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view?usp=sharing"}
_bk2 = queries.book_detail
queries.book_detail = lambda u, bid: dict(_bk2(u, bid), file_url=FILES.get(bid))
_lib.set_file = lambda u, b, url: FILES.__setitem__(b, (url or "").strip() or None)
SOURCES = {8: "https://ficbook.net/readfic/1"}  # «Где читать» — до перезапуска; у книги 8 есть всё: ficbook, файл, «Следующая»
_bk4 = queries.book_detail
queries.book_detail = lambda u, bid: dict(_bk4(u, bid), **({"source_url": SOURCES[bid]} if bid in SOURCES else {}))
_lib.set_source = lambda u, b, url: SOURCES.__setitem__(b, (url or "").strip() or None)
# Настройки книги: тип (книга/фанфик) и аннотации запоминаются до перезапуска
EDITS = {}
_bk3 = queries.book_detail
queries.book_detail = lambda u, bid: dict(_bk3(u, bid), **EDITS.get(bid, {}))
_lib.save_book = lambda u, b, f: EDITS.setdefault(b, {}).update(
    {k: (f.get(k) or "").strip() or None for k in ("kind", "title_ru") if k in f},
    **({"description_ru": (f["annotation"] or "").strip() or None} if "annotation" in f else {}),
    # статус, оценка, «избранное» — чтобы на локальном сайте было видно, что нажатие сработало
    **({"status": f["status"]} if f.get("status") else {}),
    **({"rating": float(f["rating"]) if f["rating"] else None} if "rating" in f else {}),
    **({"is_favorite": f["is_favorite"] == "on"} if "is_favorite" in f else {}))
# Отзыв после прочтения — запоминается до перезапуска; у книги 9 уже заполнен, у 7 — пусто.
# «Прочитано» на странице книги открывает окно отзыва (как на сайте, когда статус только что сменился)
REVIEWS = {9: {"summary": "Кассандра служит богу смерти и ищет убийцу. Медленно, мрачно, а финал ||убийца — её наставник, и она его отпускает||.\nВторая книга — обязательно.",
               "is_spoiler": False, "moods": ["dark", "tense", "emotional"], "pace": "medium", "driven": "mix",
               "liked": ["characters", "atmosphere"], "reread": "maybe"}}
BOOK_TROPES = {9: ["враги → возлюбленные", "морально серый герой"]}
MY_TROPES = ["ангст", "слоуберн", "враги → возлюбленные"]
_bk5 = queries.book_detail
queries.book_detail = lambda u, bid: dict(_bk5(u, bid), review=REVIEWS.get(bid), tropes=BOOK_TROPES.get(bid, []))
queries.tropes = lambda u: MY_TROPES
_sb = _lib.save_book
_lib.save_book = lambda u, b, f: (_sb(u, b, f), f.get("status") == "finished")[1]
def _save_review(u, bid, f):
    REVIEWS[bid] = {"summary": (f.get("summary") or "").strip() or None, "is_spoiler": bool(f.get("is_spoiler")),
                    "moods": [m for m in f.getlist("moods") if m in _lib.MOODS], "liked": [x for x in f.getlist("liked") if x in _lib.LIKED],
                    **{k: f.get(k) or None for k in ("pace", "driven", "reread")}}
    tr = [t.strip() for t in f.getlist("tropes") + (f.get("new_tropes") or "").split(",") if t.strip()]
    BOOK_TROPES[bid] = list(dict.fromkeys(tr))
    MY_TROPES[:] = list(dict.fromkeys(MY_TROPES + tr))
    if f.get("rating"):
        EDITS.setdefault(bid, {})["rating"] = float(f["rating"])
    print("REVIEW", bid, ascii(REVIEWS[bid]), ascii(BOOK_TROPES[bid]))
_lib.save_review = _save_review
_lib.delete_review = lambda u, bid: (REVIEWS.pop(bid, None), BOOK_TROPES.pop(bid, None))
# Подборки — в памяти до перезапуска. Порядок «последней» — по счётчику TICK (как added_at)
import itertools as _it
_tick = _it.count(100)
COLS = {1: {"id": 1, "name": "Тёмная академия", "color": "lilac", "books": {9: 5, 1: 4, 300: 3}, "t": 5},
        2: {"id": 2, "name": "Перечитать", "color": "mint", "books": {7: 2}, "t": 2},
        3: {"id": 3, "name": "Ангст, чтобы плакать", "color": "peach", "books": {}, "t": 1}}
def _colbk(bid):
    return B(bid, "finished" if bid % 2 else "want_to_read", cov=COV if bid % 3 else None)
_ord = lambda: sorted(COLS.values(), key=lambda c: -c["t"])
queries.collections = lambda u: [dict(id=c["id"], name=c["name"], color=c["color"], n=len(c["books"]),
                                      covers=[_colbk(b) for b, _ in sorted(c["books"].items(), key=lambda x: -x[1])][:3]) for c in _ord()]
queries.book_collections = lambda u, bid: [dict(id=c["id"], name=c["name"], color=c["color"], has=bid in c["books"]) for c in _ord()]
queries.collection = lambda u, cid: (lambda c: c and {"id": c["id"], "name": c["name"], "color": c["color"]})(COLS.get(cid))
queries.collection_books = lambda u, cid: [_colbk(b) for b, _ in sorted(COLS[cid]["books"].items(), key=lambda x: -x[1])]
def _create_col(u, name, bid=None):
    name = _lib._collection_name(name)
    if any(c["name"].lower() == name.lower() for c in COLS.values()):
        raise _lib.ValidationError(f"Подборка «{name}» уже есть")
    cid = max(COLS) + 1; t = next(_tick)
    COLS[cid] = {"id": cid, "name": name, "color": _lib.COLLECTION_COLORS[len(COLS) % 6], "books": {bid: t} if bid else {}, "t": t}
    return {"id": cid, "name": name, "color": COLS[cid]["color"]}
def _toggle_col(u, cid, bid, on):
    c = COLS[cid]
    if on:
        c["books"][bid] = c["t"] = next(_tick)
    else:
        c["books"].pop(bid, None)
_lib.create_collection = _create_col
_lib.set_in_collection = _toggle_col
_lib.update_collection = lambda u, cid, name, color: COLS[cid].update(name=_lib._collection_name(name), color=color)
_lib.delete_collection = lambda u, cid: COLS.pop(cid, None)
# Поиск в Hardcover — выдуманные результаты; «Добавить» открывает книгу 6 или фанфик 27
from services import catalog as _cat, hardcover_api as _hc
_hc.search = lambda q: [{"id": 900 + i, "title": f"{q} — вариант {i}", "authors": "SenLinYu", "year": 2021, "pages": 800,
                         "series": None, "cover": COV if i % 2 else None} for i in range(3)]
_cat.known = lambda u, ids: {}
_cat.add_from_hardcover = lambda u, hid, kind="book": (print("ADD", hid, kind), 27 if kind == "fanfic" else 6)[1]
# Фанфик вручную: форма проверяется, сохранения нет — открывается выдуманный фанфик 27
from services import ficbook as _fic
_fic.save_fanfic = lambda u, f: (print("FANFIC", _fic.parse(f)), 27)[1]

# «Отправить на Kindle» без настоящего Gmail: письмо не уходит, только печатается
from services import kindle as _kindle
for _k in _kindle.KEYS: os.environ[_k] = "fake"
os.environ["KINDLE_EMAIL"] = "me_fake@kindle.com"
_kindle.send = lambda data, name, title="": (print("KINDLE", name, len(data)), "me_fake@kindle.com")[1]

import uvicorn
from main import app
from fastapi.responses import RedirectResponse as _Redir
@app.get("/fake/home/{mode}")
def _fake_home(mode: str):
    """Главная без «Читаю» (empty) или ещё и без очереди «Следующие» (nonext); normal — как обычно"""
    HOME_MODE[0] = mode
    return _Redir("/", 303)
uvicorn.run(app, host="127.0.0.1", port=8011)

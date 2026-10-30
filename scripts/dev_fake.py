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
queries.fanfics = lambda u: [B(100 + i, st, kind="fanfic") for i, st in enumerate(["reading"] + ["want_to_read"] * 12 + ["finished"] * 9)]

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
              "in_library": True, "my_genre_id": 1, "notes": "", "my_description": "Спустя десять лет после окончания войны в волшебном мире назревает скандал. В Британии орудует сеть контрабандистов, торгующая артефактами и порталами.\n\nГлавной неожиданностью становится приказ «сверху»: включить в группу Драко Малфоя.\n\nНикто не знает, где он пропадал десять лет. Его досье запечатано, доступ запрещён даже Поттеру. Малфой возвращается изменившимся — спокойным, уверенным профессионалом.\n\nИ чем глубже они продвигаются в деле, тем очевиднее: самые охраняемые тайны Министерства меркнут перед напряжением между бывшими врагами." if bid == 27 else None, "is_favorite": bid == 6,
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
    h["shelf"] = {"fav": [{"id": 3, "key": "s3", "is_series": True, "title": "Crowns of Nyaxia",
                           "books": [{"id": 60 + j, "title": "x", "cover_url": COV, "pages": 400 + 60 * j} for j in range(4)]}]
                         + [k(B(200 + i, "finished", cov=COV if i % 2 else None, is_favorite=True)) for i in range(9)],
                  "reading": [k(B(1, "reading", cov=COV)), k(B(2, "reading", kind="fanfic"))],
                  "want": [k(B(300 + i, "want_to_read", is_next=True)) for i in range(5)]}
    return h
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

_lib.set_next = lambda u, b, on: print("NEXT", b, on)
_bk = queries.book_detail
queries.book_detail = lambda u, bid: dict(_bk(u, bid), status="want_to_read", is_next=bid == 8) if bid in (8, 10) else _bk(u, bid)
_b2 = queries.books
queries.books = lambda u: [dict(b, is_next=b["status"] == "want_to_read" and b["id"] % 5 == 0,
                                title_ru="Змея и крылья ночи" if b["id"] % 3 == 1 else None) for b in _b2(u)]
_lib.save_tags = lambda b, f: print("TAGS", b, dict(f))
_lib.delete_book = lambda u, b: (print("DELETE", b), "fanfic")[1]
_lib.set_series_extra = lambda u, s, b, extra: EXTRA.__setitem__(b, extra)
_lib.remove_from_series = lambda s, b: print("REMOVE", s, b)
_lib.delete_series = lambda s: print("DELETE SERIES", s)
_lib.set_cover = lambda b, url: print("COVER", b, _lib.cover_link(url))
FILES = {6: "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view?usp=sharing"}
_bk2 = queries.book_detail
queries.book_detail = lambda u, bid: dict(_bk2(u, bid), file_url=FILES.get(bid))
_lib.set_file = lambda u, b, url: FILES.__setitem__(b, (url or "").strip() or None)

# «Отправить на Kindle» без настоящего Gmail: письмо не уходит, только печатается
from services import kindle as _kindle
for _k in _kindle.KEYS: os.environ[_k] = "fake"
os.environ["KINDLE_EMAIL"] = "me_fake@kindle.com"
_kindle.send = lambda data, name, title="": (print("KINDLE", name, len(data)), "me_fake@kindle.com")[1]

import uvicorn
from main import app
uvicorn.run(app, host="127.0.0.1", port=8011)

"""Мастерская epub: главы и оглавление, склейка разорванных абзацев, обложка (обрезка под Kindle),
название/автор/серия из карточки, номера страниц для Kindle. Всё в памяти — файлы на сайте не хранятся.

Главы ищем по тексту абзаца: «Глава 5», «Глава первая», «1 глава», «Пролог», «Эпилог», «Часть II», «Аннотация».
Страницы — как в старой «Страницы для Kindle.html»: невидимые метки <a id> через N знаков
и список страниц в toc.ncx (EPUB 2) и в nav (EPUB 3)."""
import base64
import html
import io
import posixpath
import re
import zipfile
from urllib.parse import quote, unquote, urldefrag

import httpx
from PIL import Image

MAX_EPUB = 50 * 1024 * 1024
MAX_UNPACKED = 300 * 1024 * 1024  # защита от «zip-бомбы»
MAX_IMAGE = 15 * 1024 * 1024


class EpubError(Exception):
    """Понятное сообщение для пользователя: что не так с файлом."""


# ------------------------------------------------------------------ поиск глав

ORD = r"(?:[а-яё]+\s+)?[а-яё]+(?:ая|ья|яя)"  # «первая», «двадцать первая», «третья»
HEAD = re.compile(
    r"^(?:пролог|эпилог|аннотация|annotation|предисловие|послесловие|интерлюдия|от автора|бонус\w*"
    rf"|глава\s+(?:\d+|[ivxlc]+|{ORD})(?=$|[\s.:,—-]).*"
    rf"|\d+\s+глава|часть\s+(?:\d+|[ivxlc]+|{ORD})(?=$|[\s.:,—-]).*)$",
    re.I,
)
# <p>/<div> без вложенных <p>/<div> внутри — один абзац
INNER = r"((?:(?!<(?:p|div)\b|</(?:p|div)>).)*?)"
LEAF = re.compile(rf"<(p|div)\b([^>]*)>{INNER}</\1>", re.S)
STYLE = ('<style type="text/css">h2.fx-ch{page-break-before:always;text-align:center;'
         'font-weight:bold;font-size:1.3em;margin:1.5em 0 1em;text-indent:0}</style>')
PAGE_MARK = re.compile(r'<a id="(?:(?:kpl-)*page-|fxpg)\d+"></a>')  # метки старой страницы и наши
BLOCK = re.compile(r"<(br|p|div|h[1-6]|li|blockquote)\b", re.I)
# Абзац занимает на экране больше своих знаков: отступ и недописанная последняя строка.
# Без этой добавки страница с диалогами выходит на полтора экрана, а со сплошным текстом — на один
PARA = 20
VOID = {"br", "img", "hr", "meta", "link", "input", "col", "area", "base", "wbr", "source"}
NBSP = r"(?:&nbsp;|&#160;|&#xa0;|[    　])"  # неразрывные и «широкие» пробелы


def plain(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def text_len(s: str) -> int:
    """Видимые знаки куска текста между тегами (пробелы схлопнуты)."""
    return len(re.sub(r"\s+", " ", re.sub(r"&[#\w]+;", "x", s)).strip())


def plural(n: int, one: str, few: str, many: str) -> str:
    return one if n % 10 == 1 and n % 100 != 11 else few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def drop_repeat(prev: str, nxt: str) -> str:
    """После PDF на стыке строк слова повторяются: «отвези нас в | нас в больницу».
    Если начало следующего куска (1–3 слова) повторяет конец предыдущего — убираем повтор."""
    tail = prev.lower().split()
    for k in (3, 2, 1):
        words = tail[-k:]
        m = re.match(r"\s*" + r"\s+".join(re.escape(w) for w in words) + r"(?=[\s,.!?…»\"<]|$)", nxt, re.I)
        if len(tail) >= k and m and "<" not in m.group(0):
            return nxt[m.end():].lstrip()
    return nxt


def is_head(s: str) -> bool:
    return 0 < len(s) <= 80 and bool(HEAD.match(s))


def head_title(s: str) -> str:
    return "Аннотация" if s.lower() == "annotation" else s


# ------------------------------------------------------------------ книга

class Book:
    def __init__(self, data: bytes):
        if len(data) > MAX_EPUB:
            raise EpubError("Файл больше 50 МБ — это точно epub?")
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            raise EpubError("Файл не открывается как epub (это не zip-архив)")
        if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED:
            raise EpubError("Внутри файла слишком много данных")
        self.files = {i.filename: z.read(i) for i in z.infolist() if not i.is_dir()}
        m = re.search(r'full-path="([^"]+)"', self.text("META-INF/container.xml") or "")
        if not m or m.group(1) not in self.files:
            raise EpubError("Не найдено описание книги (OPF) — похоже, это не epub")
        self.opf_path = m.group(1)
        self.base = posixpath.dirname(self.opf_path)
        self.opf = self.text(self.opf_path)
        self.items = {}  # id -> {path, type, props}
        for tag in re.findall(r"<(?:opf:)?item\b[^>]*>", self.opf):
            a = dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))
            if "id" in a and "href" in a:
                self.items[a["id"]] = {"path": self.path(self.opf_path, a["href"]), "type": a.get("media-type", ""),
                                       "props": a.get("properties", "").split()}
        self.spine = [self.items[i]["path"] for i in re.findall(r'<(?:opf:)?itemref\b[^>]*\bidref="([^"]+)"', self.opf)
                      if i in self.items and "html" in self.items[i]["type"] and self.items[i]["path"] in self.files]
        self.ncx = next((v["path"] for v in self.items.values() if "dtbncx" in v["type"]), None)
        self.nav = next((v["path"] for v in self.items.values() if "nav" in v["props"]), None)
        self.version = (re.search(r'<(?:opf:)?package\b[^>]*\bversion="([\d.]+)"', self.opf) or [None, "2.0"])[1]
        if not self.spine:
            raise EpubError("В книге не нашлось ни одной страницы с текстом")

    def text(self, path: str) -> str | None:
        data = self.files.get(path)
        return None if data is None else data.decode("utf-8-sig", "replace")

    def put(self, path: str, text: str):
        self.files[path] = text.encode("utf-8")

    @staticmethod
    def path(from_file: str, href: str) -> str:
        """Ссылка внутри файла from_file -> путь в архиве."""
        return posixpath.normpath(posixpath.join(posixpath.dirname(from_file), unquote(html.unescape(href))))

    @staticmethod
    def rel(from_file: str, to_path: str) -> str:
        return quote(posixpath.relpath(to_path, posixpath.dirname(from_file) or "."), safe="/")

    def save(self) -> bytes:
        self.put(self.opf_path, self.opf)
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
            for name, data in self.files.items():
                if name != "mimetype":
                    z.writestr(name, data)
        return out.getvalue()

    # ---- что написано в файле

    def meta(self) -> dict:
        def one(tag):
            m = re.search(rf"<dc:{tag}\b[^>]*>(.*?)</dc:{tag}>", self.opf, re.S)
            return plain(m.group(1)) if m else ""
        series = re.search(r'<meta name="calibre:series" content="([^"]*)"', self.opf)
        index = re.search(r'<meta name="calibre:series_index" content="([^"]*)"', self.opf)
        return {"title": one("title"), "language": one("language"),
                "authors": [plain(a) for a in re.findall(r"<dc:creator\b[^>]*>(.*?)</dc:creator>", self.opf, re.S)],
                "series": html.unescape(series.group(1)) if series else "",
                "series_index": f"{float(index.group(1)):g}" if index and re.fullmatch(r"[\d.]+", index.group(1)) else ""}

    def toc(self) -> list[dict]:
        """Оглавление как есть: [{title, path, frag}]."""
        if self.ncx and self.text(self.ncx):
            nav_map = re.search(r"<navMap>.*</navMap>", self.text(self.ncx), re.S)  # без pageList
            pts = re.findall(r"<text>(.*?)</text>\s*</navLabel>\s*<content\s+src=\"([^\"]+)\"",
                             nav_map.group(0) if nav_map else "", re.S)
        elif self.nav:
            m = re.search(r'<nav\b[^>]*epub:type="toc".*?</nav>', self.text(self.nav), re.S)
            pts = [(t, h) for h, t in re.findall(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', m.group(0) if m else "", re.S)]
        else:
            return []
        src = self.ncx if self.ncx and self.text(self.ncx) else self.nav
        out = []
        for title, href in pts:
            target, frag = urldefrag(href)
            out.append({"title": plain(title), "path": self.path(src, target), "frag": frag})
        return out

    def cover_path(self) -> str | None:
        img = [v for v in self.items.values() if v["type"].startswith("image/") and v["path"] in self.files]
        found = next((v for v in img if "cover-image" in v["props"]), None)
        m = re.search(r'<meta\b[^>]*name="cover"[^>]*content="([^"]+)"', self.opf) or \
            re.search(r'<meta\b[^>]*content="([^"]+)"[^>]*name="cover"', self.opf)
        if not found and m:
            found = self.items.get(m.group(1)) or next((v for v in img if v["path"].endswith(m.group(1))), None)
        return found["path"] if found and found["type"].startswith("image/") else None

    def has_pages(self) -> str | None:
        """None — страниц нет; 'ours' — поставлены нами или старой страницей (можно заменить); 'own' — свои у книги."""
        listed = bool(self.ncx and "<pageTarget" in (self.text(self.ncx) or "")) or \
            bool(self.nav and re.search(r'epub:type="page-list"', self.text(self.nav) or ""))
        if not listed:
            return None
        return "ours" if any(PAGE_MARK.search(self.text(p)) for p in self.spine) else "own"

    def chapter_sizes(self, toc: list[dict]) -> list[int]:
        """Сколько знаков в каждом пункте оглавления (для подбора «знаков на страницу»)."""
        starts = {}
        for i, t in enumerate(toc):
            starts.setdefault((t["path"], t["frag"]), i)
        sizes, cur, para = [0] * len(toc), -1, False
        for p in self.spine:
            doc = self.text(p)
            cur = starts.get((p, ""), cur)
            for tok in re.split(r"(<[^>]+>)", doc[max(doc.find("<body"), 0):]):
                if tok.startswith("<"):
                    m = re.search(r'\bid="([^"]+)"', tok)
                    if m:
                        cur = starts.get((p, m.group(1)), cur)
                    para = para or bool(BLOCK.match(tok))
                elif cur >= 0 and (n := text_len(tok)):
                    sizes[cur] += n + (PARA if para else 0)
                    para = False
        return sizes

    # ---- главы

    def text_docs(self) -> list[str]:
        return [p for p in self.spine if p != self.nav]

    def join_broken(self) -> int:
        """Склеивает соседние абзацы: первый оборван (без точки и т.п.), второй — с маленькой буквы."""
        joins = 0
        ok = lambda a, b: (a and b and not is_head(a) and not is_head(b) and re.search(r"[\w,]$", a)
                           and re.match(r"[а-яёa-z]", b) and "http" not in a + b)
        for p in self.text_docs():
            doc = self.text(p)
            blocks, out, pos, i = list(LEAF.finditer(doc)), [], 0, 0
            while i < len(blocks):  # по порядку: абзац + следующие за ним куски, пока они продолжение
                m, j = blocks[i], i
                inner, a = m.group(3), plain(m.group(3))
                while j + 1 < len(blocks):
                    nx = blocks[j + 1]
                    if nx.group(1) != m.group(1) or doc[blocks[j].end():nx.start()].strip() or not ok(a, plain(nx.group(3))):
                        break
                    rest = drop_repeat(a, nx.group(3).lstrip())
                    inner = inner.rstrip() + ("" if re.match(r"[,.!?…;:»\"]", rest) else " ") + rest
                    a, j = plain(inner), j + 1
                if j > i:
                    out += [doc[pos:m.start()], f"<{m.group(1)}{m.group(2)}>{inner}</{m.group(1)}>"]
                    pos, joins = blocks[j].end(), joins + j - i
                i = j + 1
            self.put(p, "".join(out) + doc[pos:])
        return joins

    def fix_indents(self) -> int:
        """Убирает неразрывные пробелы в начале абзаца: отступ задаёт стиль, а пробелы его удваивают —
        и при выравнивании по ширине отступы выходят разной длины."""
        n = 0

        def strip(m):
            nonlocal n
            n += 1
            return m.group(1)
        for p in self.text_docs():
            # только если дальше текст: абзац из одного &nbsp; — это пустая строка-разделитель, её не трогаем
            self.put(p, re.sub(rf"(<(?:p|div)\b[^>]*>)(?:\s|{NBSP})*{NBSP}(?:\s|{NBSP})*(?![\s<]|{NBSP})", strip, self.text(p)))
        return n

    def empty_lines(self) -> tuple[int, int]:
        """(пустых абзацев-разделителей, абзацев с текстом)."""
        empty = text = 0
        for p in self.text_docs():
            for m in LEAF.finditer(self.text(p)):
                if "<img" in m.group(3):
                    continue
                if plain(m.group(3)):
                    text += 1
                else:
                    empty += 1
        return empty, text

    def remove_empty_lines(self) -> int:
        n = 0

        def drop(m):
            nonlocal n
            if "<img" in m.group(3) or plain(m.group(3)):
                return m.group(0)
            n += 1
            return ""
        for p in self.text_docs():
            self.put(p, LEAF.sub(drop, self.text(p)))
        return n

    def text_language(self) -> str | None:
        """'ru', если текст в основном кириллицей, иначе None (не угадываем)."""
        sample = "".join(plain(self.text(p)) for p in self.spine[:8])[:200000]
        cyr, lat = len(re.findall(r"[а-яё]", sample, re.I)), len(re.findall(r"[a-z]", sample, re.I))
        return "ru" if cyr > 3 * lat and cyr > 500 else None

    def has_toc_page(self) -> bool:
        """Есть ли в самой книге страница «Содержание» (со ссылками на главы)."""
        for p in self.spine:
            doc = self.text(p)
            links = {urldefrag(h)[0] for h in re.findall(r'<a\b[^>]*href="([^"#][^"]*)"', doc) if "://" not in h}
            if len(links) >= 3 and len(plain(doc)) < 5000:
                return True
        return False

    def mid_file(self, toc: list[dict]) -> int:
        """Сколько глав начинается посреди файла (до метки уже есть текст) — такие не с новой страницы."""
        n = 0
        for t in toc:
            doc = self.text(t["path"]) if t["frag"] else None
            at = doc.find(f'id="{t["frag"]}"') if doc else -1
            if at > 0 and len(plain(doc[max(doc.find("<body"), 0):at])) > 100:
                n += 1
        return n

    def add_toc_page(self, toc: list[dict]):
        """Страница «Содержание» со ссылками на главы — перед первой главой."""
        if not toc:
            return
        page = posixpath.join(self.base, "fx_toc.xhtml")
        items = "".join(f'<li><a href="{self.rel(page, t["path"])}{"#" + t["frag"] if t["frag"] else ""}">'
                        f'{html.escape(t["title"])}</a></li>' for t in toc)
        lang = self.meta()["language"] or "ru"
        self.put(page, '<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml" '
                       f'lang="{lang}" xml:lang="{lang}"><head><title>Содержание</title>'
                       '<style type="text/css">h2{text-align:center;margin:1em 0}ol{list-style:none;padding:0}'
                       'li{margin:.45em 0}a{text-decoration:none}</style></head>'
                       f'<body><h2>Содержание</h2><ol>{items}</ol></body></html>')
        first = toc[0]["path"]
        first_id = next((k for k, v in self.items.items() if v["path"] == first), None)
        self.opf = re.sub(r"(</(?:opf:)?manifest>)", r'<item id="fx-toc" href="fx_toc.xhtml" media-type="application/xhtml+xml"/>\1',
                          self.opf, count=1)
        ref = '<itemref idref="fx-toc"/>'
        if first_id and re.search(rf'<(?:opf:)?itemref\b[^>]*\bidref="{re.escape(first_id)}"', self.opf):
            self.opf = re.sub(rf'(<(?:opf:)?itemref\b[^>]*\bidref="{re.escape(first_id)}"[^>]*>)', ref + r"\1", self.opf, count=1)
        else:
            self.opf = re.sub(r"(<(?:opf:)?spine\b[^>]*>)", r"\1" + ref, self.opf, count=1)
        if re.search(r"<(?:opf:)?guide\b", self.opf):
            self.opf = re.sub(r"(<(?:opf:)?guide\b[^>]*>)", r'\1<reference type="toc" title="Содержание" href="fx_toc.xhtml"/>',
                              self.opf, count=1)
        self.items["fx-toc"] = {"path": page, "type": "application/xhtml+xml", "props": []}
        self.spine.insert(self.spine.index(first) if first in self.spine else 0, page)

    def mark_chapters(self) -> list[dict]:
        """Абзацы «Глава 5» и т.п. -> <h2 class="fx-ch">. Возвращает оглавление."""
        toc, n = [], 0

        def to_head(m):
            nonlocal n
            t = plain(m.group(3))
            if not is_head(t) or "href=" in m.group(3):  # ссылка — это пункт чужого оглавления
                return m.group(0)
            n += 1
            return f'<h2 class="fx-ch" id="fx{n}">{html.escape(head_title(t), quote=False)}</h2>'

        def existing(m):  # уже заголовок (например, «Annotation») — тоже в оглавление
            nonlocal n
            t = plain(m.group(3))
            if not is_head(t) or "fx-ch" in m.group(2):
                return m.group(0)
            n += 1
            return f'<{m.group(1)} class="fx-ch" id="fx{n}">{html.escape(head_title(t), quote=False)}</{m.group(1)}>'

        for p in self.text_docs():
            doc = self.text(p)
            doc = LEAF.sub(to_head, doc)
            doc = re.sub(r"<(h[1-3])\b([^>]*)>(.*?)</\1>", existing, doc, flags=re.S)
            if "annotation" in p.lower() and "fx-ch" not in doc:  # отдельный файл аннотации без заголовка
                n += 1
                doc = re.sub(r"(<body\b[^>]*>)", rf'\1<h2 class="fx-ch" id="fx{n}">Аннотация</h2>', doc, count=1)
            if "fx-ch" in doc and "h2.fx-ch" not in doc:
                doc = doc.replace("</head>", STYLE + "</head>", 1)
            for m in re.finditer(r'<h[1-3] class="fx-ch" id="([^"]+)">(.*?)</h[1-3]>', doc):
                toc.append({"title": html.unescape(m.group(2)), "path": p, "frag": m.group(1)})
            self.put(p, doc)
        return toc

    def write_toc(self, toc: list[dict]):
        if self.ncx and self.text(self.ncx):
            pts = "".join(f'<navPoint id="fxnp{i}" playOrder="{i}"><navLabel><text>{html.escape(t["title"])}</text></navLabel>'
                          f'<content src="{self.rel(self.ncx, t["path"])}#{t["frag"]}"/></navPoint>\n'
                          for i, t in enumerate(toc, 1))
            self.put(self.ncx, re.sub(r"<navMap>.*</navMap>", lambda _: f"<navMap>\n{pts}</navMap>",
                                      self.text(self.ncx), count=1, flags=re.S))
        if self.nav:
            lis = "".join(f'<li><a href="{self.rel(self.nav, t["path"])}#{t["frag"]}">{html.escape(t["title"])}</a></li>'
                          for t in toc)
            self.put(self.nav, re.sub(r'(<nav\b[^>]*epub:type="toc"[^>]*>.*?<ol\b[^>]*>).*?(</ol>\s*</nav>)',
                                      lambda m: m.group(1) + lis + m.group(2), self.text(self.nav), count=1, flags=re.S))

    def split_chapters(self, toc: list[dict]) -> int:
        """Каждая глава — в свой файл: так она точно начнётся с новой страницы в любой читалке.
        Режем перед элементом с id из оглавления (своим заголовком или меткой из старого оглавления).
        Открытые обёртки (<div class="section">) закрываются в конце куска и открываются заново в следующем.
        Ссылки на перенесённые id (сноски, оглавление) переписываются. Возвращает, сколько файлов добавилось."""
        moved, origin, added = {}, {}, 0  # (старый путь, id) -> новый путь; новый путь -> старый
        for p in list(self.spine):
            frags = {t["frag"] for t in toc if t["path"] == p and t["frag"]}
            if not frags:
                continue
            doc = self.text(p)
            b0, b1 = re.search(r"<body\b[^>]*>", doc), doc.rfind("</body>")
            if not b0 or b1 < 0:
                continue
            head, tail = doc[:b0.end()], doc[b1:]
            parts, stack, cur = [], [], []
            for tok in re.split(r"(<!--.*?-->|<[^>]+>)", doc[b0.end():b1], flags=re.S):
                mid = re.match(r'<[a-zA-Z][^>]*\bid="([^"]+)"', tok)
                if mid and mid.group(1) in frags and plain("".join(cur)):
                    parts.append("".join(cur) + "".join(f"</{n}>" for n, _ in reversed(stack)))
                    cur = [re.sub(r'\s+id="[^"]*"', "", t) for _, t in stack]
                cur.append(tok)
                m = re.match(r"<(/?)([a-zA-Z][\w:-]*)", tok)
                if m:
                    name = m.group(2).lower()
                    if m.group(1):
                        idx = next((i for i in range(len(stack) - 1, -1, -1) if stack[i][0] == name), None)
                        if idx is not None:
                            del stack[idx:]
                    elif name not in VOID and not tok.endswith("/>"):
                        stack.append((name, tok))
            parts.append("".join(cur))
            if len(parts) < 2:
                continue
            item_id = next(k for k, v in self.items.items() if v["path"] == p)
            stem, ext = posixpath.splitext(p)
            new_items, new_refs, paths = "", "", []
            for i, part in enumerate(parts):
                path = p if i == 0 else f"{stem}_fx{i}{ext}"
                self.put(path, head + part + tail)
                if i:
                    origin[path] = p
                    paths.append(path)
                    for x in re.findall(r'\bid="([^"]+)"', part):
                        moved[(p, x)] = path
                    new_items += f'<item id="{item_id}_fx{i}" href="{self.rel(self.opf_path, path)}" media-type="application/xhtml+xml"/>'
                    new_refs += f'<itemref idref="{item_id}_fx{i}"/>'
                    self.items[f"{item_id}_fx{i}"] = {"path": path, "type": "application/xhtml+xml", "props": []}
            self.opf = re.sub(rf'(<(?:opf:)?item\b[^>]*\bid="{re.escape(item_id)}"[^>]*>)', lambda m: m.group(1) + new_items,
                              self.opf, count=1)
            self.opf = re.sub(rf'(<(?:opf:)?itemref\b[^>]*\bidref="{re.escape(item_id)}"[^>]*>)', lambda m: m.group(1) + new_refs,
                              self.opf, count=1)
            at = self.spine.index(p) + 1
            self.spine[at:at] = paths
            added += len(paths)
        if not moved:
            return 0

        def fix(doc_path):
            base = origin.get(doc_path, doc_path)  # ссылка «#id» в куске — на исходный файл

            def repl(m):
                target = self.path(base, m.group(2)) if m.group(2) else base
                new = moved.get((target, m.group(3)))
                return m.group(0) if not new else f'{m.group(1)}="{self.rel(doc_path, new)}#{m.group(3)}"'
            self.put(doc_path, re.sub(r'(href|src)="([^"#]*)#([^"]+)"', repl, self.text(doc_path)))
        for d in set(self.spine) | {x for x in (self.ncx, self.nav) if x}:
            fix(d)
        for t in toc:
            t["path"] = moved.get((t["path"], t["frag"]), t["path"])
        return added

    # ---- страницы для Kindle

    def remove_pages(self):
        for p in self.spine:
            self.put(p, PAGE_MARK.sub("", self.text(p)))
        if self.ncx:
            self.put(self.ncx, re.sub(r"\s*<pageList>.*?</pageList>", "", self.text(self.ncx), flags=re.S))
        if self.nav:
            self.put(self.nav, re.sub(r'<nav\b[^>]*epub:type="page-list".*?</nav>\s*', "", self.text(self.nav), flags=re.S))

    def add_pages(self, per_page: int) -> int:
        """Метка <a id="fxpgN"> через каждые per_page знаков (абзац — плюс PARA) — у ближайшего абзаца или <br>."""
        # Страница рвётся только в начале абзаца, т.е. в среднем на полабзаца позже порога —
        # порог сдвигаем на полабзаца раньше, чтобы средняя страница была ровно per_page
        sizes = self.chapter_sizes([{"path": self.spine[0], "frag": ""}])
        blocks = sum(len(re.findall(r"<(?:p|div|li|blockquote|h[1-6])\b[^>]*>\s*[^<\s]|<br\b[^>]*>\s*[^<\s]", self.text(p)))
                     for p in self.spine)
        per_page = max(100, per_page - (sizes[0] / blocks / 2 if blocks else 0))
        pages, counter, para = [], 0, False
        for p in self.spine:
            doc = self.text(p)
            at = doc.find("<body")
            if at < 0:
                continue
            out = [doc[:at]]
            for tok in re.split(r"(<!--.*?-->|<[^>]+>)", doc[at:], flags=re.S):
                if tok.startswith("<") and BLOCK.match(tok):
                    para = True
                    if counter >= per_page or (not pages and counter > 0):
                        pages.append((p, f"fxpg{len(pages) + 1}"))
                        counter = 0
                        anchor = f'<a id="{pages[-1][1]}"></a>'
                        # у <br> и самозакрытых — рядом, у открывающего блока — внутри него
                        out.append(anchor + tok if tok.lower().startswith("<br") or tok.endswith("/>") else tok + anchor)
                        continue
                if not tok.startswith("<") and (n := text_len(tok)):
                    counter += n + (PARA if para else 0)
                    para = False
                out.append(tok)
            self.put(p, "".join(out))
        if not pages:
            return 0
        if self.ncx and self.text(self.ncx):
            ncx = self.text(self.ncx)
            top = max([0] + [int(x) for x in re.findall(r'playOrder="(\d+)"', ncx)])
            targets = "\n".join(f'<pageTarget id="pt-{fid}" type="normal" value="{i}" playOrder="{top + i}">'
                                f'<navLabel><text>{i}</text></navLabel><content src="{self.rel(self.ncx, p)}#{fid}"/></pageTarget>'
                                for i, (p, fid) in enumerate(pages, 1))
            ncx = ncx.replace("</navMap>", f"</navMap>\n<pageList><navLabel><text>Pages</text></navLabel>\n{targets}\n</pageList>", 1)
            ncx = re.sub(r'(name="dtb:(?:totalPageCount|maxPageNumber)" content=")\d*', rf"\g<1>{len(pages)}", ncx)
            self.put(self.ncx, ncx)
        if self.nav and self.version.startswith("3"):
            nav = self.text(self.nav)
            if "xmlns:epub=" not in nav:
                nav = re.sub(r"<html\b", '<html xmlns:epub="http://www.idpf.org/2007/ops"', nav, count=1)
            items = "".join(f'<li><a href="{self.rel(self.nav, p)}#{fid}">{i}</a></li>' for i, (p, fid) in enumerate(pages, 1))
            self.put(self.nav, nav.replace("</body>", f'<nav epub:type="page-list" hidden="hidden"><ol>{items}</ol></nav>\n</body>', 1))
        return len(pages)

    def set_language(self, lang: str):
        """Язык книги в описании и у каждой страницы (был неправильный — например, en у русского текста)."""
        if re.search(r"<dc:language\b", self.opf):
            self.opf = re.sub(r"(<dc:language\b[^>]*>).*?(</dc:language>)", lambda m: m.group(1) + lang + m.group(2),
                              self.opf, count=1, flags=re.S)
        else:
            self.opf = re.sub(r"(<(?:opf:)?metadata\b[^>]*>)", rf"\1<dc:language>{lang}</dc:language>", self.opf, count=1)
        for p in self.spine:
            self.put(p, re.sub(r"<html\b[^>]*>", lambda m: re.sub(r'\b((?:xml:)?lang=")[^"]*"', rf'\g<1>{lang}"', m.group(0)),
                               self.text(p), count=1))

    def add_lang(self, lang: str):
        """lang у каждой страницы — Kindle по нему переносит слова."""
        for p in self.spine:
            doc = self.text(p)
            if not re.search(r"<html\b[^>]*\blang=", doc):
                self.put(p, re.sub(r"<html\b", f'<html lang="{lang}" xml:lang="{lang}"', doc, count=1))

    # ---- название, автор, серия

    def set_meta(self, title: str, authors: list[str], series: str, index: str, language: str):
        opf, esc = self.opf, lambda s: html.escape(s, quote=True)
        add = []
        if title:
            opf = re.sub(r"\s*<dc:title\b[^>]*>.*?</dc:title>", "", opf, flags=re.S)
            opf = re.sub(r'\s*<meta name="calibre:title_sort"[^>]*/>', "", opf)
            add.append(f"<dc:title>{esc(title)}</dc:title>")
        if authors:
            ids = re.findall(r'<dc:creator\b[^>]*\bid="([^"]+)"', opf)
            opf = re.sub(r"\s*<dc:creator\b[^>]*>.*?</dc:creator>", "", opf, flags=re.S)
            for i in ids:  # EPUB 3: роль и сортировка автора — отдельными meta
                opf = re.sub(rf'\s*<meta\b[^>]*refines="#{re.escape(i)}"[^>]*>.*?</meta>', "", opf, flags=re.S)
            for i, a in enumerate(authors, 1):
                if self.version.startswith("3"):
                    add.append(f'<dc:creator id="fx-author{i}">{esc(a)}</dc:creator>'
                               f'<meta refines="#fx-author{i}" property="role" scheme="marc:relators">aut</meta>')
                else:
                    role = ' opf:role="aut"' if "xmlns:opf" in opf else ""
                    add.append(f"<dc:creator{role}>{esc(a)}</dc:creator>")
        if series:
            opf = re.sub(r'\s*<meta name="calibre:series(?:_index)?"[^>]*/>', "", opf)
            add.append(f'<meta name="calibre:series" content="{esc(series)}"/>')
            if index:
                add.append(f'<meta name="calibre:series_index" content="{esc(index)}"/>')
            if self.version.startswith("3"):
                ids = re.findall(r'<meta\b[^>]*property="belongs-to-collection"[^>]*\bid="([^"]+)"', opf)
                opf = re.sub(r'\s*<meta\b[^>]*property="belongs-to-collection"[^>]*>.*?</meta>', "", opf, flags=re.S)
                for i in ids:
                    opf = re.sub(rf'\s*<meta\b[^>]*refines="#{re.escape(i)}"[^>]*>.*?</meta>', "", opf, flags=re.S)
                add.append(f'<meta property="belongs-to-collection" id="fx-series">{esc(series)}</meta>'
                           '<meta refines="#fx-series" property="collection-type">series</meta>'
                           + (f'<meta refines="#fx-series" property="group-position">{esc(index)}</meta>' if index else ""))
        if language and not re.search(r"<dc:language\b", opf):
            add.append(f"<dc:language>{esc(language)}</dc:language>")
        self.opf = re.sub(r"(<(?:opf:)?metadata\b[^>]*>)", lambda m: m.group(1) + "\n    " + "\n    ".join(add), opf, count=1)
        if title and self.ncx and self.text(self.ncx):  # название и в шапке оглавления
            self.put(self.ncx, re.sub(r"(<docTitle>\s*<text>).*?(</text>)", lambda m: m.group(1) + esc(title) + m.group(2),
                                      self.text(self.ncx), count=1, flags=re.S))

    # ---- обложка

    def set_cover(self, image: bytes | None, box: tuple | None) -> str:
        path = self.cover_path()
        if path:
            src = image or self.files[path]
            self.files[path] = crop(src, box, "PNG" if path.lower().endswith(".png") else "JPEG")
            return "обложка заменена" if image else "обложка обрезана"
        if not image:
            return "в файле нет обложки — выбери картинку"
        # обложки нет: картинка + страница-обложка первой в книге
        img, page = posixpath.join(self.base, "fx_cover.jpg"), posixpath.join(self.base, "fx_cover.xhtml")
        self.files[img] = crop(image, box, "JPEG")
        self.put(page, '<?xml version="1.0" encoding="utf-8"?>\n<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Cover</title>'
                       '<style type="text/css">@page{margin:0}body{margin:0;text-align:center}img{max-width:100%;max-height:100%}</style>'
                       '</head><body><div><img src="fx_cover.jpg" alt="cover"/></div></body></html>')
        props = ' properties="cover-image"' if self.version.startswith("3") else ""
        opf = re.sub(r"(</(?:opf:)?manifest>)", f'<item id="fx-cover-img" href="fx_cover.jpg" media-type="image/jpeg"{props}/>'
                     r'<item id="fx-cover" href="fx_cover.xhtml" media-type="application/xhtml+xml"/>\1', self.opf, count=1)
        opf = re.sub(r"(</(?:opf:)?metadata>)", r'<meta name="cover" content="fx-cover-img"/>\1', opf, count=1)
        opf = re.sub(r"(<(?:opf:)?spine\b[^>]*>)", r'\1<itemref idref="fx-cover"/>', opf, count=1)
        if re.search(r"<(?:opf:)?guide\b", opf):
            opf = re.sub(r"(<(?:opf:)?guide\b[^>]*>)", r'\1<reference type="cover" title="Cover" href="fx_cover.xhtml"/>', opf, count=1)
        self.opf = opf
        return "обложка добавлена"


def crop(data: bytes, box: tuple | None, fmt: str) -> bytes:
    """box — доли картинки (x, y, ширина, высота) от 0 до 1, как выбрала в рамке."""
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except OSError:
        raise EpubError("Картинка обложки не открывается")
    im = im.convert("RGB")
    if box:
        w, h = im.size
        x, y, bw, bh = (max(0.0, min(1.0, v)) for v in box)
        im = im.crop((round(x * w), round(y * h), round(min(1, x + bw) * w), round(min(1, y + bh) * h)))
    out = io.BytesIO()
    im.save(out, fmt, quality=92)
    return out.getvalue()


def fetch_image(url: str) -> bytes:
    """Картинка по ссылке (обложка из карточки или из вариантов)."""
    if not url.startswith(("https://", "http://")):
        raise EpubError("Нужна ссылка на картинку (https://…)")
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": "BookApp/0.1"})
        r.raise_for_status()
    except httpx.HTTPError:
        raise EpubError("Не получилось скачать картинку обложки — выбери другую")
    if len(r.content) > MAX_IMAGE:
        raise EpubError("Картинка обложки больше 15 МБ")
    return r.content


# ------------------------------------------------------------------ для страницы

def card_meta(b: dict) -> dict:
    """Название, автор, серия из карточки книги — подставляются в файл."""
    authors = [a.strip() for a in (b.get("authors") or "").split(",") if a.strip() and "(перевод)" not in a]
    s = (b.get("series") or [None])[0]
    pos = s.get("sort_position") if s else None
    return {"title": b.get("title_ru") or b["title"], "authors": authors,
            "series": (s.get("name_ru") or s["name"]) if s else "",
            "series_index": f"{float(pos):g}" if pos is not None else ""}


FIXES = ("lang", "toc", "split", "toc_page", "join", "indents", "empty")  # галочки «починить»


def diagnose(data: bytes) -> dict:
    """Пробный прогон всех исправлений на копии: что не так и сколько всего поправится."""
    book, dry = Book(data), Book(data)
    toc = book.toc()
    empty, text = dry.empty_lines()
    # пустая строка между почти каждыми абзацами; в фанфиках с ficbook текст в <br>, абзацев мало — их не трогаем
    many_empty = text >= 200 and empty > 0.3 * text
    if many_empty:
        dry.remove_empty_lines()
    indents = dry.fix_indents()
    joins = dry.join_broken()
    found = dry.mark_chapters() if len(toc) < 3 else toc
    rebuild = len(toc) < 3 and len(found) >= 3
    chapters = found if rebuild else toc
    return {"book": book, "toc": toc, "chapters": chapters, "rebuild": rebuild, "joins": joins, "indents": indents,
            "empty": empty if many_empty else 0, "mid": (dry if rebuild else book).mid_file(chapters),
            "toc_page": book.has_toc_page(), "sizes": (dry if rebuild else book).chapter_sizes(chapters),
            "lang_text": book.text_language()}


def checks(d: dict, cover_size, ratio: float = 0.73) -> list[dict]:
    """Проверка файла строками: state ok / warn / bad, detail — что не так (у «ok» пусто),
    action — что сделаю, key — галочка «починить» (fix — она же, если её стоит включить)."""
    book, toc, ch = d["book"], d["toc"], d["chapters"]
    meta, out = book.meta(), []
    add = lambda state, title, detail="", action="", key="": out.append(
        {"state": state, "title": title, "detail": detail if state != "ok" else "", "action": action,
         "key": key, "fix": key if state != "ok" else ""})
    if not cover_size:
        add("bad", "Обложка", "нет", "выбрать в шаге 3")
    else:
        r = cover_size[0] / cover_size[1]
        add("warn" if abs(r - ratio) > 0.02 else "ok", "Обложка", f"пропорция {r:.2f}", "обрезать в шаге 3")
    if d["rebuild"]:
        add("bad", "Оглавление", f"в тексте {len(ch)} глав, в оглавлении {len(toc)}", "собрать из глав", "toc")
    elif len(toc) >= 3:
        add("ok", "Оглавление", key="toc")
    else:
        add("warn", "Оглавление", "почти пустое, а глав в тексте не нашлось")
    if len(ch) >= 3:
        mid = len(ch) if d["rebuild"] else d["mid"]
        add("bad" if d["rebuild"] or mid >= max(2, len(ch) / 3) else "ok", "Главы с новой страницы",
            f"{mid} из {len(ch)} идут сплошным текстом", "разложить по файлам", "split")
        add("ok" if d["toc_page"] else "warn", "Страница «Содержание»", "отсутствует", "добавить", "toc_page")
    add("bad" if d["joins"] else "ok", "Разорванные абзацы", f"{d['joins']} шт.", "склеить", "join")
    add("warn" if d["indents"] > 10 else "ok", "Отступы", f"разной длины ({d['indents']} абзацев)", "убрать лишние пробелы", "indents")
    if d["empty"]:
        add("warn", "Пустые строки", f"между абзацами ({d['empty']} шт.)", "убрать", "empty")
    lang = meta["language"]
    wrong = bool(d["lang_text"] and not lang.lower().startswith(d["lang_text"]))
    add("bad" if wrong else "ok", "Язык", f"указан «{lang or 'нет'}», а текст на русском", "исправить на «ru»", "lang")
    if not meta["authors"]:
        add("warn", "Автор", "не указан", "вписать в шаге 2")
    elif any(re.search(r"[а-яёa-z][А-ЯЁA-Z]", a) for a in meta["authors"]):
        add("warn", "Автор", f"склеено: «{', '.join(meta['authors'])}»", "поправить в шаге 2")
    if re.search(r"\(.*?\)|\bтн-?\s*\d|\.(?:epub|fb2)$|_", meta["title"], re.I):
        add("warn", "Название", f"«{meta['title']}»", "поправить в шаге 2")
    pages = book.has_pages()
    add("ok" if pages == "own" else "warn", "Номера страниц",
        "есть, поставлены мастерской" if pages == "ours" else "в файле нет списка страниц",
        "пересчитать" if pages == "ours" else "поставить", "" if pages == "own" else "pages")
    return out


def inspect(data: bytes) -> dict:
    """Что внутри файла и что мастерская в нём найдёт — до изменений."""
    d = diagnose(data)
    book, toc = d["book"], d["toc"]
    before = book.chapter_sizes(toc) if toc else []
    cover = book.cover_path()
    thumb = size = None
    if cover:
        try:
            im = Image.open(io.BytesIO(book.files[cover]))
            size = im.size
            im = im.convert("RGB")
            im.thumbnail((900, 1300))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
            thumb = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except OSError:
            pass
    found = checks(d, size)
    total = sum(len(plain(book.text(p)[max(book.text(p).find("<body"), 0):])) for p in book.spine)
    return {"meta": book.meta(), "version": book.version, "toc_before": len(toc), "rebuild": d["rebuild"],
            "chapters": [{"title": t["title"], "chars": n} for t, n in zip(d["chapters"], d["sizes"])],
            "before": [{"title": t["title"], "chars": n} for t, n in zip(toc, before)],
            "checks": found, "recommend": sorted({c["fix"] for c in found if c["fix"]}),
            "counts": {"joins": d["joins"], "indents": d["indents"], "empty": d["empty"], "mid": d["mid"],
                       "toc_page": d["toc_page"]},
            "query": search_query(book.meta()), "cover": thumb, "cover_size": size, "pages": book.has_pages(),
            "chars": total, "weight": sum(d["sizes"]) or total}


def search_query(meta: dict) -> str:
    """Название из файла без «(ЛП)», «тн-3» и т.п. — для поиска книги."""
    title = re.sub(r"\(.*?\)|\[.*?\]|\bтн-?\s*[\d.,]+|\.(?:epub|fb2)$", " ", meta["title"], flags=re.I)
    return re.sub(r"\s+", " ", title).strip(" -—.,_")


def build(data: bytes, *, fixes: set[str], title: str, authors: list[str], series: str, index: str,
          cover: bytes | None, box: tuple | None, change_cover: bool, per_page: int | None) -> tuple[bytes, list[str]]:
    """fixes — галочки шага 4 (FIXES). Порядок важен: сначала чистка текста, потом главы, потом страницы."""
    book = Book(data)
    report = []
    lang = book.text_language()
    if "lang" in fixes and lang and not book.meta()["language"].lower().startswith(lang):
        report.append(f"язык: был «{book.meta()['language'] or 'не указан'}», стал «{lang}»")
        book.set_language(lang)
    if "empty" in fixes and (n := book.remove_empty_lines()):
        report.append(f"убрано пустых строк: {n}")
    if "indents" in fixes and (n := book.fix_indents()):
        report.append(f"выровнены отступы: {n}")
    if "join" in fixes and (n := book.join_broken()):
        report.append(f"склеено разорванных абзацев: {n}")
    toc = book.toc()
    rebuilt = False
    if "toc" in fixes and len(toc) < 3:
        found = book.mark_chapters()
        if len(found) >= 3:
            toc, rebuilt = found, True
        else:
            report.append("главы в тексте не нашлись — оглавление не меняла")
    if "split" in fixes and toc and (n := book.split_chapters(toc)):
        report.append(f"главы с новой страницы: +{n} файлов")
    if rebuilt:
        book.write_toc(toc)
        report.append(f"оглавление: {len(toc)} пунктов")
    if "toc_page" in fixes and toc and not book.has_toc_page():
        book.add_toc_page(toc)
        report.append("добавлена страница «Содержание»")
    book.set_meta(title, authors, series, index, "")
    book.add_lang((lang or book.meta()["language"] or "ru").split("-")[0])
    if change_cover:
        report.append(book.set_cover(cover, box))
    if per_page:
        state = book.has_pages()
        if state == "own":
            report.append("в книге свои номера страниц — их не трогала")
        else:
            if state == "ours":
                book.remove_pages()
            n = book.add_pages(per_page)
            report.append(f"страниц для Kindle: {n} (по {per_page} знаков)" if n else "текста для страниц не нашлось")
    return book.save(), report

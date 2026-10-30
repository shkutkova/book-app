// Мастерская epub: файл -> /workshop/inspect (проверка) -> поиск книги (/workshop/find, /workshop/pick)
// -> обложка, главы, страницы -> /workshop/build -> скачивание. Файл держит браузер; сервер ничего не хранит.
(() => {
  const $ = id => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const form = $('ws');
  let bookId = form.dataset.book;  // книга сайта: из карточки или выбранная в поиске
  const remember = (k, v) => { try { localStorage.setItem('ws-' + k, v); } catch {} };
  const recall = k => { try { return localStorage.getItem('ws-' + k); } catch { return null; } };
  const plural = (n, one, few, many) => n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many;
  let info = null, variants = null;  // variants — обложки выбранной книги (null — ещё не спрашивали)

  // ---- 1. файл и проверка
  const fileInput = $('ws-file'), drop = $('ws-drop');
  ['dragenter', 'dragover'].forEach(t => drop.addEventListener(t, () => drop.classList.add('over')));
  ['dragleave', 'drop'].forEach(t => drop.addEventListener(t, () => drop.classList.remove('over')));
  fileInput.addEventListener('change', async () => {
    const f = fileInput.files[0];
    if (!f) return;
    drop.querySelector('b').textContent = f.name;
    drop.querySelector('b + span').textContent = ' — нажми, чтобы выбрать другой';
    $('ws-info').textContent = 'Смотрю, что внутри…';
    $('ws-check').hidden = $('ws-rest').hidden = $('ws-report').hidden = true; $('ws-state').textContent = '';
    const fd = new FormData(); fd.append('file', f);
    try {
      const data = await (await fetch('/workshop/inspect', {method: 'POST', body: fd})).json();
      if (data.error) { $('ws-info').textContent = data.error; return; }
      info = data; showInfo();
    } catch { $('ws-info').textContent = 'Не получилось связаться с сервером — попробуй ещё раз.'; }
  });

  const MARK = {ok: '✓', warn: '!', bad: '✕'};
  function showInfo() {
    const m = info.meta;
    $('ws-info').textContent = `«${m.title || 'без названия'}»` + (m.authors.length ? ` — ${m.authors.join(', ')}` : '') +
      ` · ${Math.round(info.chars / 1000)} тыс. знаков`;
    // проверка и ремонт: галочка «починить» стоит там, где нашлась проблема
    const bad = info.checks.filter(c => c.state !== 'ok').length;
    $('ws-check-title').textContent = bad ? `Проверка и ремонт — есть что поправить (${bad})` : 'Проверка — всё в порядке';
    fixes = Object.fromEntries(info.checks.filter(c => c.key).map(c => [c.key, !!c.fix]));
    if (fixes.pages && recall('pages') === '0') fixes.pages = false;  // сняла когда-то сама — не навязываем
    renderChecks();
    bar($('map-before'), info.before.length ? info.before : [{title: 'нет оглавления', chars: info.chars}]);
    bar($('map-after'), info.rebuild && info.chapters.length >= 3 ? info.chapters : info.before);
    $('ws-check').hidden = false;

    $('ws-filemeta').textContent = 'В файле сейчас: ' + [m.title, m.authors.join(', '), m.series && `${m.series}${m.series_index ? ' #' + m.series_index : ''}`]
      .filter(Boolean).join(' · ');
    if (!bookId) {  // без карточки — поля из файла, и сразу ищем, что это за книга
      $('ws-title').value = info.query || m.title; $('ws-authors').value = m.authors.join(', ');
      $('ws-series').value = m.series; $('ws-index').value = m.series_index;
      $('ws-q').value = info.query; find();
    }
    $('calib-ch').replaceChildren(...info.chapters.map((c, i) => c.chars > 2000 ? new Option(`${c.title} — ${c.chars.toLocaleString('ru')} знаков`, i) : null).filter(Boolean));
    estimate();
    // обложка: из карточки / найденной книги, если есть, иначе — как в файле
    ($('chip-found').hidden ? form.querySelector('[name=cover_src][value=keep]') : $('src-card')).checked = true;
    coverSource();
    $('ws-rest').hidden = false;
  }

  // ---- строки проверки: сверху «В порядке» значками, ниже — что поправить, у каждой строки галочка
  let fixes = {};
  function fixBox(c) {  // круглая галочка «починить»; состояние помним в fixes
    const label = el('label', 'ws-fixbox');
    const box = el('input'); box.type = 'checkbox'; box.name = c.key; box.checked = fixes[c.key];
    box.onchange = () => {
      fixes[c.key] = box.checked;
      if (c.key === 'pages') { remember('pages', box.checked ? '1' : '0'); $('ws-pages-opts').hidden = !box.checked; }
    };
    label.append(box, el('span', null, c.action));
    return label;
  }
  function tocList() {  // главы, как они будут в оглавлении
    const ol = el('ol', 'ws-toc');
    ol.append(...info.chapters.map(c => el('li', null, c.title)));
    return ol;
  }
  function renderChecks() {
    const box = $('ws-checks'), opts = $('ws-pages-opts');
    opts.hidden = true;  // покажется в строке «Номера страниц», если галочка стоит
    const ok = info.checks.filter(c => c.state === 'ok'), todo = info.checks.filter(c => c.state !== 'ok');
    const parts = [];
    if (ok.length) {
      const line = el('div', 'ws-ok-line'), list = tocList();
      list.hidden = true;
      for (const c of ok) {
        if (c.title === 'Оглавление' && info.chapters.length) {  // по клику — список глав под строкой значков
          const b = el('button', 'ws-ok ws-ok-toc', `✓ ${c.title} (${info.chapters.length}) ▾`);
          b.type = 'button'; b.setAttribute('aria-expanded', 'false');
          b.onclick = () => {
            list.hidden = !list.hidden; b.setAttribute('aria-expanded', String(!list.hidden));
            b.textContent = `✓ ${c.title} (${info.chapters.length}) ${list.hidden ? '▾' : '▴'}`;
          };
          line.append(b);
        } else {
          line.append(el('span', 'ws-ok', '✓ ' + c.title));
        }
      }
      parts.push(el('h4', null, 'В порядке'), line, list);
    }
    if (todo.length) parts.push(el('h4', null, 'Что поправить'));
    for (const c of todo) {
      const r = el('div', 'ws-row st-' + c.state);
      r.append(el('span', 'mark', MARK[c.state]), el('b', null, c.title), el('span', 'detail', c.detail),
               c.key ? fixBox(c) : el('span', 'ws-hint', '→ ' + c.action));
      if (c.key === 'toc' && info.chapters.length) {  // собираем заново — сразу видно, какие будут главы
        const d = el('details', 'ws-row-more');
        d.append(el('summary', null, `Как будет: ${info.chapters.length} ${plural(info.chapters.length, 'глава', 'главы', 'глав')}`), tocList());
        r.append(d);
      }
      if (c.key === 'pages') { r.append(opts); opts.hidden = !fixes.pages; }
      parts.push(r);
    }
    box.replaceChildren(...parts);
  }

  function bar(box, parts) {  // полоса книги: отрезок — глава; наведение, клик или касание — название под полосами
    const total = parts.reduce((s, p) => s + p.chars, 0) || 1;
    const show = (s, title) => {
      document.querySelectorAll('.ws-bar span.on').forEach(x => x.classList.remove('on'));
      s.classList.add('on'); $('bar-label').textContent = title;
    };
    box.replaceChildren(...parts.map((p, i) => {
      const s = el('span'); s.style.flexGrow = Math.max(p.chars / total, 0.004); s.title = p.title;
      s.tabIndex = 0; s.className = i % 2 ? 'alt' : '';
      ['mouseenter', 'click', 'focus'].forEach(t => s.addEventListener(t, () => show(s, p.title)));
      return s;
    }));
    $('bar-label').textContent = '';
  }

  // ---- 2. что за книга
  $('ws-find').addEventListener('click', find);
  $('ws-q').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); find(); } });
  async function find() {
    const q = $('ws-q').value.trim(), state = $('ws-find-state'), box = $('ws-results');
    if (!q) return;
    state.textContent = 'Ищу…'; box.replaceChildren();
    try {
      const data = await (await fetch('/workshop/find?' + new URLSearchParams({q}))).json();
      for (const r of data.results) {
        const b = el('button', 'ws-hit'); b.type = 'button';
        const img = el('span', 'ws-hit-cover');
        if (r.cover) { const i = el('img'); i.src = r.cover; i.alt = ''; i.loading = 'lazy'; i.onerror = () => i.remove(); img.append(i); }
        const t = el('span', 'ws-hit-text');
        t.append(el('b', null, r.title), el('span', 'muted small', [r.authors, r.series, r.year].filter(Boolean).join(' · ')),
                 el('span', 'badge' + (r.in_library ? ' finished' : ''), r.in_library ? 'в моих книгах' : r.source));
        b.append(img, t);
        b.onclick = () => pick(r, b);
        box.append(b);
      }
      state.textContent = (data.results.length ? 'Нажми на свою — подставлю название, автора, серию и обложки.' : 'Ничего не нашлось — попробуй название на английском или автора.')
        + (data.failed.length ? ` Не ответили: ${data.failed.join(', ')}.` : '');
    } catch { state.textContent = 'Не получилось поискать — попробуй ещё раз.'; }
  }

  async function pick(r, btn) {
    $('ws-results').querySelectorAll('.on').forEach(x => x.classList.remove('on')); btn.classList.add('on');
    const state = $('ws-find-state');
    let meta = {title: r.title, authors: r.authors ? r.authors.split(', ') : [], series: '', series_index: ''}, cover = r.cover;
    variants = r.cover ? [{url: r.cover, source: r.source, label: ''}] : [];
    if (r.book_id || r.hc_id) {
      state.textContent = 'Подтягиваю данные и обложки…';
      try {
        const data = await (await fetch('/workshop/pick?' + new URLSearchParams(r.book_id ? {book: r.book_id} : {hc: r.hc_id}))).json();
        if (data.error) { state.textContent = data.error; return; }
        meta = data.meta; cover = data.cover; variants = data.covers;
        state.textContent = `Подставила. Обложек на выбор: ${variants.length}.`;
      } catch { state.textContent = 'Не получилось подтянуть данные — заполни поля сама.'; }
    }
    bookId = r.book_id || '';
    $('ws-title').value = meta.title || ''; $('ws-authors').value = (meta.authors || []).join(', ');
    $('ws-series').value = meta.series || ''; $('ws-index').value = meta.series_index || '';
    $('chip-found').hidden = !cover; $('chip-variants').hidden = variants.length < 2;
    $('src-card').dataset.url = cover || '';
    $('chip-found-text').textContent = r.book_id ? 'Из карточки' : 'Найденной книги';
    renderVariants();
    (cover ? $('src-card') : form.querySelector('[name=cover_src][value=keep]')).checked = true;
    coverSource();
  }

  // ---- 3. обложка
  const img = $('crop-img'), frame = $('crop-frame'), ratioIn = $('ratio'), cropOn = $('crop-on');
  ratioIn.value = recall('ratio') || ratioIn.value;
  let box = null;  // рамка в долях картинки: x, y, w (высота — из пропорции)

  form.querySelectorAll('[name=cover_src]').forEach(r => r.addEventListener('change', coverSource));
  function coverSource() {
    const r = form.querySelector('[name=cover_src]:checked');
    $('ws-variants').hidden = $('ws-variants-state').hidden = r.id !== 'src-variant';
    $('crop-empty').hidden = true;
    if (r.value === 'keep') {
      if (info?.cover) show(info.cover);
      else { hideCrop(); $('crop-empty').hidden = false; $('crop-empty').textContent = 'В файле нет обложки — найди книгу (шаг 2) или выбери свою картинку.'; }
    } else if (r.id === 'src-card') {
      $('ws-cover-url').value = r.dataset.url; show(r.dataset.url);
    } else if (r.id === 'src-variant') {
      loadVariants();
      const on = $('ws-variants').querySelector('.on');
      $('ws-cover-url').value = on ? on.dataset.url : '';
      if (on) show(on.dataset.url); else hideCrop();
    } else if (r.value === 'file') {
      const f = $('ws-cover-file').files[0];
      if (f) show(URL.createObjectURL(f)); else { hideCrop(); $('ws-cover-file').click(); }
    }
  }
  $('ws-cover-file').addEventListener('change', () => { $('src-file').checked = true; coverSource(); });

  async function loadVariants() {  // книга из карточки: варианты спрашиваем при первом открытии
    if (variants || !bookId) return;
    variants = [];
    $('ws-variants-state').textContent = 'Ищу варианты…';
    try { variants = (await (await fetch('/workshop/pick?' + new URLSearchParams({book: bookId}))).json()).covers || []; } catch {}
    renderVariants();
  }
  function renderVariants() {
    const grid = $('ws-variants');
    grid.replaceChildren(...(variants || []).map(c => {
      const b = el('button', 'pick'); b.type = 'button'; b.title = c.label || ''; b.dataset.url = c.url;
      const i = el('img'); i.alt = ''; i.loading = 'lazy'; i.src = c.url; i.onerror = () => b.remove();
      b.append(i, el('span', 'src', c.source));
      b.onclick = () => {
        grid.querySelectorAll('.on').forEach(x => x.classList.remove('on')); b.classList.add('on');
        $('src-variant').checked = true; $('ws-cover-url').value = c.url; show(c.url);
      };
      return b;
    }));
    $('ws-variants-state').textContent = variants?.length ? 'Нажми на понравившуюся.' : 'Вариантов не нашлось.';
  }

  function hideCrop() { $('ws-cropper').hidden = true; img.removeAttribute('src'); }
  function show(src) {
    $('ws-cropper').hidden = false;
    img.onload = () => { box = null; fit(); };
    img.onerror = () => { hideCrop(); $('crop-empty').hidden = false; $('crop-empty').textContent = 'Картинка не открылась — выбери другую.'; };
    img.src = src;
  }
  const ratio = () => Math.min(1.5, Math.max(0.4, parseFloat(ratioIn.value) || 0.73));
  // высота рамки в долях: ширина рамки в пикселях / пропорция / высота картинки
  const fh = b => b.w * img.naturalWidth / ratio() / img.naturalHeight;
  function fit() {  // самая большая рамка по центру
    if (!img.naturalWidth) return;
    let w = 1;
    if (fh({w}) > 1) w = img.naturalHeight * ratio() / img.naturalWidth;
    box = {w, x: (1 - w) / 2, y: (1 - fh({w})) / 2};
    draw();
  }
  function draw() {
    frame.hidden = !cropOn.checked;
    if (!box || !img.naturalWidth) return;
    const h = fh(box);
    Object.assign(frame.style, {left: box.x * 100 + '%', top: box.y * 100 + '%', width: box.w * 100 + '%', height: h * 100 + '%'});
    $('ws-crop').value = cropOn.checked ? [box.x, box.y, box.w, h].map(v => v.toFixed(4)).join(',') : '';
    const W = Math.round(box.w * img.naturalWidth), H = Math.round(h * img.naturalHeight);
    const [sw, sh] = cropOn.checked ? [W, H] : [img.naturalWidth, img.naturalHeight];
    $('crop-size').textContent = `Получится ${sw}×${sh}` + (sw < 600 ? ' — мелковато, на Kindle может быть мутной' : '');
  }
  ratioIn.addEventListener('input', () => { remember('ratio', ratioIn.value); fit(); });
  cropOn.addEventListener('change', draw);

  // перетаскивание рамки и уголка (мышь и палец)
  let drag = null;
  frame.addEventListener('pointerdown', e => {
    e.preventDefault(); frame.setPointerCapture(e.pointerId);
    drag = {resize: e.target.id === 'crop-handle', sx: e.clientX, sy: e.clientY, b: {...box},
            rw: img.clientWidth, rh: img.clientHeight};
  });
  frame.addEventListener('pointermove', e => {
    if (!drag) return;
    const dx = (e.clientX - drag.sx) / drag.rw, dy = (e.clientY - drag.sy) / drag.rh, b = drag.b;
    if (drag.resize) {
      const maxW = Math.min(1 - b.x, (1 - b.y) * img.naturalHeight * ratio() / img.naturalWidth);
      box = {...b, w: Math.max(0.15, Math.min(maxW, b.w + dx))};
    } else {
      box = {...b, x: Math.max(0, Math.min(1 - b.w, b.x + dx)), y: Math.max(0, Math.min(1 - fh(b), b.y + dy))};
    }
    draw();
  });
  ['pointerup', 'pointercancel'].forEach(t => frame.addEventListener(t, () => drag = null));

  // ---- номера страниц: «Kindle» (≈ один экран) или «Своё» число
  const perPage = $('per-page'), KINDLE = '950';
  perPage.value = recall('per-page') || KINDLE;
  let own = perPage.value !== KINDLE;
  function estimate() {
    const total = info ? (info.weight || info.chars) : 0, n = total ? Math.ceil(total / Math.max(200, +perPage.value || 950)) : 0;
    $('pages-est').textContent = n ? `≈ ${n} ${plural(n, 'страница', 'страницы', 'страниц')}` : '';
    form.querySelector('[data-per]').classList.toggle('on', !own);
    $('per-own').classList.toggle('on', own);
    $('ws-own').hidden = !own;
    if (!own) $('ws-calib').hidden = true;
  }
  perPage.addEventListener('input', () => { remember('per-page', perPage.value); estimate(); });
  form.querySelector('[data-per]').addEventListener('click', () => { own = false; perPage.value = KINDLE; perPage.dispatchEvent(new Event('input')); });
  $('per-own').addEventListener('click', () => { own = true; estimate(); perPage.focus(); });
  $('calib-open').addEventListener('click', () => { $('ws-calib').hidden = !$('ws-calib').hidden; });
  $('calib-go').addEventListener('click', () => {
    const c = info?.chapters[+$('calib-ch').value], n = +$('calib-n').value;
    if (!c || !n) return;
    perPage.value = Math.max(200, Math.round(c.chars / n / 10) * 10);
    perPage.dispatchEvent(new Event('input'));
  });

  // ---- скачать или отправить на Kindle: собирает сервер, файл не хранится
  function fileName() {
    const author = $('ws-authors').value.split(',')[0].trim(), title = $('ws-title').value.trim() || 'book';
    return ((author ? author + ' - ' : '') + title).replace(/[\/:*?"<>|]+/g, ' ').trim() + '.epub';
  }
  function formData() {  // null — если не выбрана картинка для обложки
    const src = form.querySelector('[name=cover_src]:checked');
    if ((src.value === 'url' && !$('ws-cover-url').value) || (src.value === 'file' && !$('ws-cover-file').files[0])) {
      $('ws-state').textContent = 'Выбери картинку для обложки (или «Как в файле»).'; return null;
    }
    const fd = new FormData(form);
    if (src.value !== 'url') fd.delete('cover_url');
    fd.append('filename', fileName());
    return fd;
  }
  function showReport(report) {
    $('ws-report').replaceChildren(...report.map(t => el('li', null, t)));
    $('ws-report').hidden = !report.length;
  }
  async function run(btn, work) {  // кнопки недоступны, пока идёт работа
    const btns = [$('ws-build'), $('ws-kindle')].filter(Boolean);
    btns.forEach(b => b.disabled = true);
    try { await work(); } catch { $('ws-state').textContent = 'Не получилось связаться с сервером — попробуй ещё раз.'; }
    finally { btns.forEach(b => b.disabled = false); }
  }

  form.addEventListener('submit', e => {
    e.preventDefault();
    if (!fileInput.files[0]) return;
    const fd = formData(), state = $('ws-state');
    if (!fd) return;
    run($('ws-build'), async () => {
      state.textContent = 'Собираю файл…';
      const r = await fetch('/workshop/build', {method: 'POST', body: fd});
      if (!r.ok) { state.textContent = (await r.json().catch(() => ({}))).error || 'Не получилось собрать файл.'; return; }
      const blob = await r.blob(), name = fd.get('filename');
      const a = Object.assign(el('a'), {href: URL.createObjectURL(blob), download: name});
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 10000);
      showReport(JSON.parse(decodeURIComponent(r.headers.get('X-Report') || '%5B%5D')));
      state.textContent = `Готово: ${name}`;
    });
  });

  $('ws-kindle')?.addEventListener('click', () => {
    if (!fileInput.files[0]) return;
    const fd = formData(), state = $('ws-state');
    if (!fd) return;
    run($('ws-kindle'), async () => {
      state.textContent = 'Собираю и отправляю на Kindle…';
      const r = await fetch('/workshop/kindle', {method: 'POST', body: fd});
      const data = await r.json().catch(() => ({}));
      if (data.report) showReport(data.report);
      state.textContent = r.ok ? `Отправлено на ${data.to} — появится на Kindle через пару минут.`
        : data.error || 'Не получилось отправить.';
    });
  });
})();

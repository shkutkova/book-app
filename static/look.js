// Вид сайта (стили — look.css): фон от цвета обложки и прокрутки, цвет названий,
// веер «Читаю сейчас», очередь «Следующие» с перетаскиванием, привидение-помощник, глаза в названии сайта.
(() => {
  const d = document.documentElement;

  // у каждого названия книги свой пастельный цвет — для контура (look.css)
  const PAST = ['#ffe08f', '#a6ecd0', '#b5dbff', '#dacbff', '#ffcdb5', '#ffc6e2'];
  document.querySelectorAll('.st-b h3, .title-block h1, .qc>b, .book-card .ttl, .s-card.soft>b, .book-link')
    .forEach((el, i) => el.style.setProperty('--tc', PAST[i % PAST.length]));

  // ---- прокрутка: --sc от 0 (верх) до 1 (низ) — по ней фон сдвигается и меняет оттенок
  const onScroll = () => d.style.setProperty('--sc', (scrollY / Math.max(1, d.scrollHeight - innerHeight)).toFixed(3));
  addEventListener('scroll', onScroll, {passive: true}); onScroll();

  // ---- фон: основа — лиловый и голубой, третье пятно — цвет обложки. Его считает сервер (/cover-tone):
  // браузеру чужую картинку читать нельзя. Цвет смягчаем — не кислотный и не тёмный; нет картинки или она серая — запасной тон
  const SOFT = ['#8f6cf0', '#4f97f0', '#1fb3cc', '#7fc24a', '#a3a35a', '#d98cc0'];  // лиловый, голубой, лазурный, салатовый, оливковый, пыльно-розовый
  const soften = ([r, g, b]) => {
    r /= 255; g /= 255; b /= 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), c = mx - mn;
    if (c < .1) return null;
    const h = ((mx === r ? ((g - b) / c) % 6 : mx === g ? (b - r) / c + 2 : (r - g) / c + 4) * 60 + 360) % 360;
    const warm = h > 25 && h < 70;  // жёлто-оранжевые приглушаем сильнее, чтобы фон не желтел
    return `hsl(${Math.round(h)} ${warm ? 42 : 58}% ${warm ? 54 : 60}%)`;
  };
  const toneOf = async el => {
    const fb = SOFT[(+el.dataset.id || 0) % 6], url = el.dataset.cover;
    if (!url) return fb;
    try { const j = await (await fetch('/cover-tone?u=' + encodeURIComponent(url))).json(); return (j.rgb && soften(j.rgb)) || fb; }
    catch { return fb; }
  };
  const amb = c => d.style.setProperty('--amb', c);
  const seg = location.pathname.split('/')[1] || '';
  let base = SOFT[({books: 2, fanfics: 5, series: 4, stats: 3, add: 1, workshop: 2})[seg] ?? 0];  // у раздела свой тон
  amb(base);
  document.querySelectorAll('.fc, .qc').forEach(el => toneOf(el).then(c => {
    el.dataset.k = c; el.style.setProperty('--k', c);
    if (el.matches('.fc.act')) amb(base = c);
  }));
  document.querySelectorAll('.qc').forEach(c => {  // наведение на карточку очереди — фон временно её цвета
    c.addEventListener('mouseenter', () => { if (c.dataset.k) amb(c.dataset.k); });
    c.addEventListener('mouseleave', () => amb(base));
  });
  if (seg === 'book' || seg === 'series') {  // страница книги или серии — цвет первой обложки на ней
    const im = document.querySelector('.wrap img[src^="http"]');
    if (im) toneOf({dataset: {id: location.pathname.split('/')[2], cover: im.src}}).then(c => amb(base = c));
  }

  // ---- веер «Читаю сейчас»: нажатая обложка выходит вперёд, остальные раскладываются слева и справа от неё
  const fan = [...document.querySelectorAll('.fc')], texts = [...document.querySelectorAll('.st-b')];
  const pick = i => {
    let n = 0;
    fan.forEach((f, j) => {
      const on = j === i;
      f.classList.toggle('act', on); texts[j]?.classList.toggle('act', on);
      if (on) { f.style.removeProperty('--s'); f.style.removeProperty('--d'); return; }
      f.style.setProperty('--s', n % 2 ? 1 : -1); f.style.setProperty('--d', (n >> 1) + 1); n++;
    });
    if (fan[i].dataset.k) amb(base = fan[i].dataset.k);
  };
  fan.forEach((f, i) => f.addEventListener('click', () => f.classList.contains('act') ? location.assign(f.dataset.href) : pick(i)));

  // ---- очередь «Следующие»: перетаскивание меняет порядок (номера пересчитываются сами), порядок сохраняется как у полки
  const q = document.querySelector('.q-row');
  if (q && window.Sortable) {
    let dragged = 0;
    q.addEventListener('click', e => { if (Date.now() - dragged < 400) e.preventDefault(); }, true);
    Sortable.create(q, {
      draggable: '.qc', forceFallback: true, fallbackTolerance: 4, delay: 220, delayOnTouchOnly: true, animation: 160, ghostClass: 'drag-ghost',
      onEnd: e => {
        dragged = Date.now();
        if (e.oldIndex === e.newIndex) return;
        const items = [...q.querySelectorAll('[data-key]')].map(x => x.dataset.key);
        fetch('/shelf/order', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({shelf: 'want', items})})
          .then(r => { if (!r.ok) throw r; window.bookAppChanged?.(); })
          .catch(() => alert('Не получилось сохранить порядок очереди. Обнови страницу и попробуй ещё раз.'));
      },
    });
  }

  // ---- привидение: подсказки приходят со страницы (#say-data, сейчас — только главная); нет подсказок — просто подпрыгивает
  const ghost = document.getElementById('ghost'), bubble = document.getElementById('say');
  if (ghost) {
    let SAY = [], i = 0, timer;
    try { SAY = JSON.parse(document.getElementById('say-data')?.textContent || '[]'); } catch {}
    const talk = () => {
      if (!SAY.length) { ghost.classList.remove('hop'); void ghost.offsetWidth; ghost.classList.add('hop'); return; }
      bubble.textContent = SAY[i++ % SAY.length];
      bubble.classList.remove('off', 'pop'); void bubble.offsetWidth; bubble.classList.add('pop');
      clearTimeout(timer); timer = setTimeout(() => bubble.classList.add('off'), 9000);
    };
    ghost.addEventListener('click', talk);
    bubble.addEventListener('click', () => bubble.classList.add('off'));
    if (SAY.length) talk(); else bubble.classList.add('off');
    // глаза привидения и «oo» в названии сайта следят за курсором
    const eyes = ghost.querySelector('.eyes'), pupils = [...document.querySelectorAll('.wm .oo b')];
    const look = (el, e, r) => {
      const b = el.getBoundingClientRect(), dx = e.clientX - b.x - b.width / 2, dy = e.clientY - b.y - b.height / 2, l = Math.hypot(dx, dy) || 1;
      return [dx / l * r, dy / l * r];
    };
    addEventListener('pointermove', e => {
      const [x, y] = look(ghost, e, 3.5); eyes.style.transform = `translate(${x}px,${y}px)`;
      pupils.forEach(p => { const [px, py] = look(p.parentNode, e, 2.2); p.style.translate = `${px}px ${py}px`; });
    }, {passive: true});
  }
})();

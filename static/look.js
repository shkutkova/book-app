// Новый вид (пробный, стили — look.css): переключатель «как сейчас / новый», фон от цвета обложки и прокрутки,
// веер «Читаю сейчас», очередь «Следующие» с перетаскиванием, привидение-помощник, глаза в названии сайта.
(() => {
  const d = document.documentElement;

  // ---- переключатель вида; выбор запоминается в браузере (ставит его до отрисовки скрипт в <head>)
  const sw = document.querySelector('.look-switch');
  const setLook = v => {
    if (v === 'new') d.dataset.look = 'new'; else delete d.dataset.look;
    try { localStorage.setItem('look', v); } catch {}
    sw?.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', b.dataset.v === v));
  };
  sw?.addEventListener('click', e => { const b = e.target.closest('button'); if (b) setLook(b.dataset.v); });
  setLook(d.dataset.look === 'new' ? 'new' : 'old');

  // ---- прокрутка: --sc от 0 (верх) до 1 (низ) — по ней фон сдвигается и меняет оттенок
  const onScroll = () => d.style.setProperty('--sc', (scrollY / Math.max(1, d.scrollHeight - innerHeight)).toFixed(3));
  addEventListener('scroll', onScroll, {passive: true}); onScroll();

  // ---- цвет книги: из картинки обложки (самые насыщенные точки весят больше); картинку прочитать нельзя или её нет — цвет по id
  const TONES = ['#8c1424', '#a87a1e', '#0f6b66', '#7d1f66', '#2a4c8a', '#2c6b3c'];
  const colorOf = el => new Promise(done => {
    const fb = TONES[(+el.dataset.id || 0) % 6], url = el.dataset.cover;
    if (!url) return done(fb);
    const im = new Image(); im.crossOrigin = 'anonymous';
    im.onerror = () => done(fb);
    im.onload = () => {
      try {
        const c = document.createElement('canvas'); c.width = c.height = 12;
        const x = c.getContext('2d'); x.drawImage(im, 0, 0, 12, 12);
        const p = x.getImageData(0, 0, 12, 12).data;
        let r = 0, g = 0, b = 0, n = 0;
        for (let i = 0; i < p.length; i += 4) {
          const w = Math.max(p[i], p[i + 1], p[i + 2]) - Math.min(p[i], p[i + 1], p[i + 2]) + 8;
          r += p[i] * w; g += p[i + 1] * w; b += p[i + 2] * w; n += w;
        }
        const k = Math.min(1.6, 150 / Math.max(r / n, g / n, b / n, 1));  // тёмную обложку высветляем, светлую приглушаем
        done(`rgb(${Math.round(r / n * k)},${Math.round(g / n * k)},${Math.round(b / n * k)})`);
      } catch { done(fb); }
    };
    im.src = url;
  });
  let base = '';
  const amb = c => c ? d.style.setProperty('--amb', c) : d.style.removeProperty('--amb');
  document.querySelectorAll('.fc, .qc').forEach(el => colorOf(el).then(c => {
    el.dataset.k = c; el.style.setProperty('--k', c);
    if (el.matches('.fc.act')) amb(base = c);
  }));
  document.querySelectorAll('.qc').forEach(c => {  // наведение на карточку очереди — фон временно её цвета
    c.addEventListener('mouseenter', () => amb(c.dataset.k));
    c.addEventListener('mouseleave', () => amb(base));
  });

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
      if (d.dataset.look !== 'new') return;
      const [x, y] = look(ghost, e, 3.5); eyes.style.transform = `translate(${x}px,${y}px)`;
      pupils.forEach(p => { const [px, py] = look(p.parentNode, e, 2.2); p.style.translate = `${px}px ${py}px`; });
    }, {passive: true});
  }
})();

// Движение: шапка при прокрутке, «наверх», отклик после сохранения, цифры досчитываются.
(() => {
  const d = document.documentElement, calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const top = () => scrollTo({top: 0, behavior: calm ? 'auto' : 'smooth'});

  // ---- шапка и «наверх»: классы на <html> по прокрутке
  let lastY = scrollY, queued = false;
  function onScroll() {
    const y = scrollY;
    d.classList.toggle('scrolled', y > 8);
    d.classList.toggle('far', y > innerHeight * 1.5);
    if (Math.abs(y - lastY) > 6) { d.classList.toggle('nav-hide', y > lastY && y > 120); lastY = y; }
    queued = false;
  }
  addEventListener('scroll', () => { if (!queued) { queued = true; requestAnimationFrame(onScroll); } }, {passive: true});
  onScroll();
  document.querySelector('.to-top')?.addEventListener('click', top);
  // нижняя панель: касание раздела, в котором уже находишься, — наверх (как в приложениях)
  document.querySelectorAll('.tabbar a.on').forEach(a => a.addEventListener('click', e => {
    if (location.pathname === new URL(a.href).pathname) { e.preventDefault(); top(); }
  }));

  // ---- свечение цветом обложки: размытая копия первой обложки в углу цветной карточки
  document.querySelectorAll('.s-card.soft, .now-card').forEach(c => {
    const img = c.querySelector('img');
    if (!img) return;
    const glow = img.cloneNode(); glow.className = 'glow-img'; glow.alt = '';
    c.prepend(glow);
  });

  // ---- отклик после сохранения: что нажала — запоминаем перед отправкой, на новой странице проигрываем
  document.addEventListener('submit', e => {
    if (e.defaultPrevented) return;
    const f = e.target;
    const kind = f.matches('.fav-corner') ? 'fav' : f.matches('.rate') ? 'rate' : f.closest('.status-menu') ? 'status' : '';
    try { if (kind) sessionStorage.setItem('fx', kind); } catch {}
  });
  let fx = '';
  try { fx = sessionStorage.getItem('fx') || ''; sessionStorage.removeItem('fx'); } catch {}
  if (fx) {
    document.querySelector({fav: '.fav-round.on', rate: '.rate', status: '.status-menu summary'}[fx])?.classList.add('pop');
  }

  // ---- цифры досчитываются: на доске главной — когда видно, в статистике — при каждой смене периода
  const NUM = /^[\d\s  ]+(?:,\d+)?$/;
  const value = t => parseFloat(t.replace(/[\s  ]/g, '').replace(',', '.'));
  function countUp(el, from = 0) {
    const text = el.textContent.trim();
    if (calm || !NUM.test(text)) return;
    const to = value(text), dec = (text.split(',')[1] || '').length;
    if (!to || to === from) return;
    const fmt = v => v.toLocaleString('ru-RU', {minimumFractionDigits: dec, maximumFractionDigits: dec});
    const t0 = performance.now(), dur = 750;
    const step = now => {
      const p = Math.min(1, (now - t0) / dur), k = 1 - Math.pow(2, -10 * p);  // быстро в начале, мягко в конце
      el._mine = el.textContent = p < 1 ? fmt(from + (to - from) * k) : text;
      if (p < 1) requestAnimationFrame(step);
    };
    el._mine = el.textContent = fmt(from);
    requestAnimationFrame(step);
  }
  const seen = new IntersectionObserver(entries => entries.forEach(en => {
    if (en.isIntersecting) { seen.unobserve(en.target); countUp(en.target); }
  }), {threshold: .6});
  document.querySelectorAll('.board .big:not(.word)').forEach(el => seen.observe(el));
  // статистика пишет цифры сама (и при смене года) — ловим запись и досчитываем от прежнего числа
  document.querySelectorAll('.kpi b').forEach(el => {
    let prev = 0;
    new MutationObserver(() => {
      if (el.textContent === el._mine) return;  // это пишем мы сами
      const text = el.textContent.trim();
      countUp(el, prev);
      prev = NUM.test(text) ? value(text) : 0;
    }).observe(el, {childList: true, characterData: true, subtree: true});
  });
})();

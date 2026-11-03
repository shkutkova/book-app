// Эффекты оформления: подсветка меню, поиск-капля, звёзды и огонёк без крутилки. Идеи — Aceternity UI, переписано без React.
(() => {
  const mouse = matchMedia('(hover: hover) and (pointer: fine)').matches;

  // ---- меню в шапке: под пунктом, на который навела, плашка его цвета — переезжает от пункта к пункту
  const links = document.querySelector('nav .links');
  if (links && mouse) {
    const hl = document.createElement('span');
    hl.className = 'nav-hl'; hl.setAttribute('aria-hidden', 'true');
    links.prepend(hl);
    const move = a => {
      const jump = !links.classList.contains('hl');   // первый раз — появляется на месте, без проезда
      hl.style.transition = jump ? 'opacity .2s' : '';
      links.style.setProperty('--hl-x', a.offsetLeft + 'px');
      links.style.setProperty('--hl-w', a.offsetWidth + 'px');
      links.style.setProperty('--hl-c', getComputedStyle(a).getPropertyValue('--sec'));
      links.classList.add('hl');
    };
    links.querySelectorAll('a').forEach(a => {
      a.addEventListener('pointerenter', () => move(a));
      a.addEventListener('focus', () => move(a));
    });
    links.addEventListener('pointerleave', () => links.classList.remove('hl'));
    links.addEventListener('focusout', e => { if (!links.contains(e.relatedTarget)) links.classList.remove('hl'); });
  }

  // ---- поиск-капля: в фокусе капля с лупой отрывается от поля вправо (SVG-фильтр #goo «склеивает» их края).
  // Есть текст — в капле крестик «очистить»
  document.querySelectorAll('input.find').forEach(inp => {
    const box = document.createElement('div');
    box.className = 'gsearch';
    box.innerHTML = '<span class="goo" aria-hidden="true"><i class="g-pill"></i><i class="g-drop"></i></span>'
      + '<button type="button" class="g-btn" tabindex="-1" aria-label="Очистить поиск">'
      + '<svg class="i-find" viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></svg>'
      + '<svg class="i-clear" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg></button>';
    inp.replaceWith(box); box.append(inp);
    const sync = () => {
      box.classList.toggle('open', document.activeElement === inp || inp.value !== '');
      box.classList.toggle('filled', inp.value !== '');
    };
    ['focus', 'blur', 'input'].forEach(ev => inp.addEventListener(ev, sync));
    addEventListener('DOMContentLoaded', sync); addEventListener('pageshow', sync);  // текст подставили из адреса или «Назад»
    box.querySelector('.g-btn').addEventListener('click', () => {
      if (inp.value) { inp.value = ''; inp.dispatchEvent(new Event('input', {bubbles: true})); }
      inp.focus(); sync();
    });
    sync();
  });

  // ---- звёзды и огонёк: без крутилки — сразу показываем новое (страница потом перезагрузится с сохранённым)
  document.addEventListener('submit', e => {
    const form = e.target, btn = e.submitter;
    if (!btn) return;
    if (form.matches('.rate')) {
      const all = [...form.querySelectorAll('button')], n = all.indexOf(btn) + 1, off = btn.value === '';
      all.forEach((b, i) => b.classList.toggle('on', !off && i < n));
      form.classList.toggle('empty', off);
      btn.classList.remove('pop'); void btn.offsetWidth; btn.classList.add('pop');
    } else if (form.matches('.fav-corner')) {
      btn.classList.toggle('on');
      btn.classList.remove('pop'); void btn.offsetWidth; btn.classList.add('pop');
    }
  });
})();

// Фильтр списков («Книги», «Фанфики», «Серии»): кнопки [data-show] оставляют одну группу
// [data-group], «Избранное» (data-show=fav) и «Следующие» (data-show=next) — отмеченные data-fav / data-next из всех групп, поле #find ищет по data-find у карточек. Выбор кнопки запоминается в адресе (#want_to_read).
(() => {
  const groups = [...document.querySelectorAll('[data-group]')];
  const buttons = [...document.querySelectorAll('[data-show]')];
  const find = document.getElementById('find');
  const nothing = document.getElementById('nothing');
  if (!buttons.length) return;
  const MARKS = ['fav', 'next'];  // не группа, а отметка у карточки
  let show = buttons.some(b => b.dataset.show === location.hash.slice(1)) ? location.hash.slice(1) : 'all';

  function apply() {
    const q = (find?.value || '').trim().toLowerCase();
    let any = false;
    buttons.forEach(b => b.setAttribute('aria-pressed', b.dataset.show === show));
    for (const g of groups) {
      let n = 0;
      for (const it of g.querySelectorAll('[data-find]')) {
        const hit = (!q || it.dataset.find.includes(q)) && (!MARKS.includes(show) || it.hasAttribute('data-' + show));
        it.hidden = !hit; n += hit;
      }
      g.hidden = (show !== 'all' && !MARKS.includes(show) && g.dataset.group !== show) || !n;
      const count = g.querySelector('.count'); if (count) count.textContent = n;
      any ||= !g.hidden;
    }
    if (nothing) nothing.hidden = any;
  }
  buttons.forEach(b => b.onclick = () => {
    show = b.dataset.show;
    history.replaceState(null, '', show === 'all' ? location.pathname : '#' + show);
    apply();
  });
  if (find) find.oninput = apply;
  apply();
})();

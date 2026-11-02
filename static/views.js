// «Книги», «Фанфики»: вид списка (карточки / лента) — запоминается в браузере.
// В ленте у описания вкладки «Аннотация | Подробнее» и «Читать полностью»
(() => {
  const lib = document.getElementById('lib');
  if (!lib) return;
  const buttons = document.querySelectorAll('.view-switch [data-view]');
  const mark = () => buttons.forEach(b => b.setAttribute('aria-pressed', b.dataset.view === lib.dataset.view));
  buttons.forEach(b => b.onclick = () => {
    lib.dataset.view = b.dataset.view;
    try { localStorage.setItem('libView', b.dataset.view); } catch {}
    mark();
  });
  mark();

  // Свечение карточки в ленте — размытая копия её обложки (видна только в ленте)
  lib.querySelectorAll('.book-card').forEach(card => {
    const img = card.querySelector('.cover img');
    if (!img) return;
    const g = document.createElement('span'), i = new Image();
    g.className = 'fglow'; i.src = img.src; i.alt = ''; i.loading = 'lazy';
    g.append(i); card.prepend(g);
  });

  lib.addEventListener('click', e => {
    const box = e.target.closest('.feed-desc');
    if (!box) return;
    const desc = box.querySelector('.desc'), toggle = box.querySelector('.desc-toggle');
    const tab = e.target.closest('[data-tab]');
    if (tab) {
      box.querySelectorAll('[data-tab]').forEach(t => {
        const on = t === tab;
        t.classList.toggle('on', on); t.setAttribute('aria-selected', on);
      });
      desc.querySelectorAll('[data-pane]').forEach(p => p.hidden = p.dataset.pane !== tab.dataset.tab);
    } else if (e.target === toggle) {
      const open = !desc.classList.toggle('clamp');
      toggle.textContent = open ? 'Свернуть' : 'Читать полностью';
      toggle.setAttribute('aria-expanded', open);
    }
  });
})();

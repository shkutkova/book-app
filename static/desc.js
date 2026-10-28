// Описание (книги, серии): сначала несколько строк, «Читать полностью» — если текст не влез.
// У книги могут быть вкладки «Подробнее | Аннотация» — при переключении сворачивается заново
(() => {
  const desc = document.getElementById('desc'), toggle = document.getElementById('desc-toggle');
  if (!desc || !toggle) return;
  const label = open => {
    toggle.textContent = open ? 'Свернуть' : 'Читать полностью';
    toggle.setAttribute('aria-expanded', open);
  };
  const measure = () => {
    desc.classList.add('clamp'); label(false);
    toggle.hidden = desc.scrollHeight <= desc.clientHeight + 4;  // влезло — сворачивать нечего
    if (toggle.hidden) desc.classList.remove('clamp');
  };
  toggle.onclick = () => label(!desc.classList.toggle('clamp'));
  document.querySelectorAll('.desc-tabs [data-tab]').forEach(tab => tab.onclick = () => {
    document.querySelectorAll('.desc-tabs [data-tab]').forEach(t => {
      const on = t === tab;
      t.classList.toggle('on', on); t.setAttribute('aria-selected', on);
    });
    desc.querySelectorAll('[data-pane]').forEach(p => p.hidden = p.dataset.pane !== tab.dataset.tab);
    measure();
  });
  measure();
})();

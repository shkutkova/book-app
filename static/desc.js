// Описание (книги, серии): сначала несколько строк, «Читать полностью» — если текст не влез
(() => {
  const desc = document.getElementById('desc'), toggle = document.getElementById('desc-toggle');
  if (!desc || !toggle) return;
  desc.classList.add('clamp');
  if (desc.scrollHeight <= desc.clientHeight + 4) { desc.classList.remove('clamp'); return; }  // влезло — сворачивать нечего
  toggle.hidden = false;
  toggle.onclick = () => {
    const open = !desc.classList.toggle('clamp');
    toggle.textContent = open ? 'Свернуть' : 'Читать полностью';
    toggle.setAttribute('aria-expanded', open);
  };
})();

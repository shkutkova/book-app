// Светящаяся рамка карточек (книги в списках, серии, «Читаю сейчас»): пятно света по краю поворачивается за курсором.
// Идея — Aceternity «Glowing effect», переписано без React. Стили — style.css (.glow).
(() => {
  if (!matchMedia('(hover: hover) and (pointer: fine)').matches) return;   // телефон: мыши нет — рамки нет
  const PROXIMITY = 64, INACTIVE = 0.01;   // рамка загорается, когда курсор ближе 64px к карточке

  const cards = [...document.querySelectorAll('.book-card, .s-card, .now-card')].map(el => {
    const g = document.createElement('span');
    g.className = 'glow'; g.setAttribute('aria-hidden', 'true');
    el.append(g);
    return {el, angle: 0, target: 0};
  });
  if (!cards.length) return;

  let px = -1e4, py = -1e4, queued = false, spinning = false;
  function update() {
    queued = false;
    for (const c of cards) {
      const r = c.el.getBoundingClientRect();
      if (!r.width || r.bottom < -PROXIMITY || r.top > innerHeight + PROXIMITY) continue;   // скрыта или за экраном
      const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
      // в самом центре угол «прыгает» — там рамку гасим
      const center = Math.hypot(px - cx, py - cy) < Math.min(r.width, r.height) / 2 * INACTIVE;
      const near = px > r.left - PROXIMITY && px < r.right + PROXIMITY && py > r.top - PROXIMITY && py < r.bottom + PROXIMITY;
      const on = near && !center;
      c.el.style.setProperty('--glow-on', on ? 1 : 0);
      if (!on) continue;
      const t = Math.atan2(py - cy, px - cx) * 180 / Math.PI + 90;
      c.target = c.angle + ((t - c.angle + 540) % 360 - 180);   // поворачиваемся коротким путём
    }
    if (!spinning) { spinning = true; requestAnimationFrame(spin); }
  }
  // плавно догоняем курсор
  function spin() {
    let moving = false;
    for (const c of cards) {
      const d = c.target - c.angle;
      if (Math.abs(d) < 0.1) continue;
      c.angle += d * 0.12; moving = true;
      c.el.style.setProperty('--glow-a', c.angle.toFixed(1));
    }
    spinning = moving;
    if (moving) requestAnimationFrame(spin);
  }
  const queue = () => { if (!queued) { queued = true; requestAnimationFrame(update); } };
  addEventListener('pointermove', e => { px = e.clientX; py = e.clientY; queue(); }, {passive: true});
  addEventListener('scroll', queue, {passive: true});
  document.addEventListener('pointerleave', () => { px = py = -1e4; queue(); });
})();

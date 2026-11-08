// Надпись на обложке (мастерская epub): название и автор на прозрачном холсте, в одном из стилей.
// o = {style, mode: top|bottom|split, color: light|dark, size: s|m|l}. Шрифты — Google Fonts (подключает workshop.html).
window.CoverText = (() => {
  const STYLES = [
    {id: 'modern', label: 'Современный'},
    {id: 'classic', label: 'Классика'},   // рамка, вензеля, антиква капителью
    {id: 'paper', label: 'Бумага'},       // название на рваной полосе бумаги
    {id: 'magazine', label: 'Журнал'},    // крупная антиква по левому краю
    {id: 'poster', label: 'Постер'},      // узкие заглавные с цветной тенью
  ];
  const FONTS = {  // [название, автор]
    modern: ['700 {s}px Unbounded', '800 {s}px Nunito'],
    classic: ['600 {s}px "Cormorant SC"', 'italic 600 {s}px "Cormorant Garamond"'],
    paper: ['500 {s}px "Cormorant Garamond"', '600 {s}px "Cormorant SC"'],
    magazine: ['700 {s}px "Playfair Display"', '800 {s}px Nunito'],
    poster: ['600 {s}px Oswald', '800 {s}px Nunito'],
  };
  const font = (style, i, s) => FONTS[style][i].replace('{s}', s.toFixed(1));
  const SIZE = {s: 0.8, m: 1, l: 1.22};
  const INK = {light: '#fbf5ec', dark: '#1d1428'};
  const SHADE = {light: '12,6,24', dark: '255,249,240'};  // подложка под текст — противоположного цвета

  function fonts(t, style) {  // дождаться шрифтов с нужными буквами (кириллица грузится отдельно)
    return Promise.all([document.fonts.load(font(style, 0, 40), t.title || 'Аа'),
                        document.fonts.load(font(style, 1, 40), t.author || 'Аа')]).catch(() => {});
  }
  function spacing(ctx, px) { try { ctx.letterSpacing = px + 'px'; } catch {} }
  function wrap(ctx, text, maxW) {  // слова по строкам, чтобы влезли в ширину
    const lines = [];
    for (const w of text.split(/\s+/)) {
      const last = lines[lines.length - 1];
      if (last && ctx.measureText(last + ' ' + w).width <= maxW) lines[lines.length - 1] = last + ' ' + w; else lines.push(w);
    }
    return lines;
  }
  function fit(ctx, text, f, track, start, maxW, maxLines, min) {  // самый крупный размер, при котором влезает
    let size = start, lines = [];
    for (; size > min; size *= 0.93) {
      ctx.font = f(size); spacing(ctx, size * track);
      lines = wrap(ctx, text, maxW);
      if (lines.length <= maxLines && lines.every(l => ctx.measureText(l).width <= maxW)) break;
    }
    return {size, lines};
  }
  function scrim(ctx, W, H, top, h, rgb, a) {  // плавное затемнение (или осветление) у края
    const g = ctx.createLinearGradient(0, top ? 0 : H, 0, top ? h : H - h);
    g.addColorStop(0, `rgba(${rgb},${a})`); g.addColorStop(.55, `rgba(${rgb},${a * .6})`); g.addColorStop(1, `rgba(${rgb},0)`);
    ctx.fillStyle = g; ctx.fillRect(0, top ? 0 : H - h, W, h);
  }
  function place(mode, H, pad, th, ah, gap) {  // верх блока названия и блока автора
    if (mode === 'top') return {ty: pad, ay: pad + th + gap};
    if (mode === 'split') return {ty: pad, ay: H - pad - ah};
    const ay = H - pad - ah;
    return {ty: ah ? ay - gap - th : H - pad - th, ay};
  }
  function scrims(ctx, W, H, o, th, ah, gap, pad, a) {
    const rgb = SHADE[o.color];
    if (o.mode === 'split') {
      if (th) scrim(ctx, W, H, true, th + pad * 3, rgb, a);
      if (ah) scrim(ctx, W, H, false, ah + pad * 3, rgb, a);
    } else scrim(ctx, W, H, o.mode === 'top', th + (ah ? gap + ah : 0) + pad * 3, rgb, a);
  }
  function lines(ctx, ls, x, y, lh, size) { ls.forEach((l, i) => ctx.fillText(l, x, y + i * lh + size * 0.82)); }
  function glow(ctx, o, W) {  // мягкая тень, чтобы буквы не терялись на пёстрой картинке
    ctx.shadowColor = o.color === 'light' ? 'rgba(0,0,0,.5)' : 'rgba(255,255,255,.45)'; ctx.shadowBlur = W * 0.012;
  }

  function paint(ctx, W, H, t, o) {
    const k = SIZE[o.size] || 1, ink = INK[o.color] || INK.light, st = o.style in FONTS ? o.style : 'modern';
    ctx.save();
    ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'center';
    ({modern, classic, paper, magazine, poster})[st](ctx, W, H, t, {...o, style: st}, k, ink);
    ctx.restore();
  }

  function modern(ctx, W, H, t, o, k, ink) {
    const pad = W * 0.08, maxW = W - pad * 2;
    const T = t.title ? fit(ctx, t.title, s => font('modern', 0, s), 0, W * 0.12 * k, maxW, 4, W * 0.035) : {size: 0, lines: []};
    const aS = W * 0.045 * k, lh = T.size * 1.12, gap = W * 0.035;
    const th = T.lines.length * lh, ah = t.author ? aS * 1.3 : 0;
    scrims(ctx, W, H, o, th, ah, gap, pad, .78);
    const {ty, ay} = place(o.mode, H, pad, th, ah, gap);
    ctx.fillStyle = ink; glow(ctx, o, W);
    ctx.font = font('modern', 0, T.size); spacing(ctx, 0); lines(ctx, T.lines, W / 2, ty, lh, T.size);
    if (ah) { ctx.font = font('modern', 1, aS); spacing(ctx, aS * 0.12); ctx.fillText(t.author.toUpperCase(), W / 2, ay + aS); }
  }

  function classic(ctx, W, H, t, o, k, ink) {
    const pad = W * 0.13, maxW = W - pad * 2;
    const T = t.title ? fit(ctx, t.title.toUpperCase(), s => font('classic', 0, s), .05, W * 0.15 * k, maxW, 3, W * 0.04) : {size: 0, lines: []};
    const aS = W * 0.058 * k, lh = T.size * 1.02, gap = W * 0.07;
    const th = T.lines.length * lh, ah = t.author ? aS * 1.3 : 0;
    scrims(ctx, W, H, o, th, ah, gap, pad, .72);
    // рамка: двойная линия с ромбиками по углам
    ctx.strokeStyle = ink; ctx.fillStyle = ink; ctx.globalAlpha = .85;
    const m1 = W * 0.035, m2 = W * 0.05;
    ctx.lineWidth = W * 0.003; ctx.strokeRect(m1, m1, W - m1 * 2, H - m1 * 2);
    ctx.lineWidth = W * 0.0012; ctx.strokeRect(m2, m2, W - m2 * 2, H - m2 * 2);
    const d = W * 0.012;
    for (const [x, y] of [[m1, m1], [W - m1, m1], [m1, H - m1], [W - m1, H - m1]]) diamond(ctx, x, y, d);
    ctx.globalAlpha = 1;
    const {ty, ay} = place(o.mode, H, pad, th, ah, gap);
    glow(ctx, o, W);
    ctx.font = font('classic', 0, T.size); spacing(ctx, T.size * .05); lines(ctx, T.lines, W / 2, ty, lh, T.size);
    if (ah) {
      ctx.font = font('classic', 1, aS); spacing(ctx, aS * .03);
      const y = ay + aS, tw = ctx.measureText(t.author).width;
      ctx.fillText(t.author, W / 2, y);
      ctx.shadowBlur = 0;  // вензель: линия — ромбик — линия по бокам имени
      const len = Math.min(W * 0.12, (maxW - tw) / 2 - W * 0.03), cy = y - aS * 0.3;
      if (len > W * 0.03) for (const s of [-1, 1]) {
        const x0 = W / 2 + s * (tw / 2 + W * 0.03);
        ctx.fillRect(Math.min(x0, x0 + s * len), cy - W * 0.0008, len, W * 0.0016);
        diamond(ctx, x0 + s * len, cy, W * 0.007);
      }
    }
  }
  function diamond(ctx, x, y, r) {
    ctx.beginPath(); ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath(); ctx.fill();
  }

  function paper(ctx, W, H, t, o, k, ink) {
    const pad = W * 0.08, maxW = W - pad * 2.4;
    const T = t.title ? fit(ctx, t.title.toUpperCase(), s => font('paper', 0, s), .06, W * 0.14 * k, maxW, 3, W * 0.04) : {size: 0, lines: []};
    const aS = W * 0.05 * k, lh = T.size * 1.0, gap = W * 0.05;
    const th = T.lines.length * lh, ah = t.author ? aS * 1.3 : 0;
    const bandPad = W * 0.07, bandH = th ? th + bandPad * 2 : 0;
    const paperC = o.color === 'light' ? '#efe6d8' : '#1e1824', textC = o.color === 'light' ? '#241a26' : '#f3ead9';
    scrims(ctx, W, H, o, bandH, ah, gap, pad * 0.5, .7);
    const {ty, ay} = place(o.mode, H, pad * 1.4, bandH, ah, gap);
    if (bandH) {  // рваная полоса бумаги во всю ширину
      let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
      const step = W / 38, amp = W * 0.018;
      ctx.beginPath(); ctx.moveTo(-5, ty + amp);
      for (let x = 0; x <= W + step; x += step) ctx.lineTo(x, ty + amp * rnd() * 1.6);
      for (let x = W + 5; x >= -step; x -= step) ctx.lineTo(x, ty + bandH - amp * rnd() * 1.6);
      ctx.closePath();
      ctx.shadowColor = 'rgba(0,0,0,.45)'; ctx.shadowBlur = W * 0.02; ctx.shadowOffsetY = W * 0.006;
      ctx.fillStyle = paperC; ctx.fill();
      ctx.shadowColor = 'transparent'; ctx.shadowOffsetY = 0;
      ctx.fillStyle = textC; ctx.font = font('paper', 0, T.size); spacing(ctx, T.size * .06);
      lines(ctx, T.lines, W / 2, ty + bandPad, lh, T.size);
    }
    if (ah) {
      ctx.fillStyle = ink; glow(ctx, o, W);
      ctx.font = font('paper', 1, aS); spacing(ctx, aS * .08); ctx.fillText(t.author, W / 2, ay + aS);
    }
  }

  function magazine(ctx, W, H, t, o, k, ink) {
    const pad = W * 0.08, maxW = W - pad * 2;
    const T = t.title ? fit(ctx, t.title, s => font('magazine', 0, s), -.01, W * 0.13 * k, maxW, 4, W * 0.04) : {size: 0, lines: []};
    const aS = W * 0.036 * k, lh = T.size * 1.06, gap = W * 0.03;
    const th = T.lines.length * lh, ah = t.author ? aS * 1.3 : 0;
    scrims(ctx, W, H, o, th, ah, gap, pad, .5);
    const {ty, ay} = place(o.mode, H, pad, th, ah, gap);
    ctx.textAlign = 'left'; ctx.fillStyle = o.color === 'light' ? '#f6e4df' : ink; glow(ctx, o, W);
    ctx.font = font('magazine', 0, T.size); spacing(ctx, -T.size * .01); lines(ctx, T.lines, pad, ty, lh, T.size);
    if (ah) { ctx.font = font('magazine', 1, aS); spacing(ctx, aS * .14); ctx.fillText(t.author.toUpperCase(), pad, ay + aS); }
  }

  function poster(ctx, W, H, t, o, k, ink) {
    const pad = W * 0.08, maxW = W - pad * 2;
    const T = t.title ? fit(ctx, t.title.toUpperCase(), s => font('poster', 0, s), .01, W * 0.24 * k, maxW, 3, W * 0.05) : {size: 0, lines: []};
    const aS = W * 0.042 * k, lh = T.size * 1.0, gap = W * 0.04;
    const th = T.lines.length * lh, ah = t.author ? aS * 1.3 : 0;
    scrims(ctx, W, H, o, th, ah, gap, pad, .6);
    const {ty, ay} = place(o.mode, H, pad, th, ah, gap);
    const main = o.color === 'light' ? '#dccbff' : '#1d1428', accent = o.color === 'light' ? '#2fc4b2' : '#ffffff';
    const off = W * 0.012;
    ctx.font = font('poster', 0, T.size); spacing(ctx, T.size * .01);
    ctx.fillStyle = accent; lines(ctx, T.lines, W / 2 + off, ty + off, lh, T.size);  // цветная тень со сдвигом
    ctx.fillStyle = main; lines(ctx, T.lines, W / 2, ty, lh, T.size);
    if (ah) {
      ctx.fillStyle = ink; glow(ctx, o, W);
      ctx.font = font('poster', 1, aS); spacing(ctx, aS * .14); ctx.fillText(t.author.toUpperCase(), W / 2, ay + aS);
    }
  }

  return {STYLES, fonts, paint};
})();

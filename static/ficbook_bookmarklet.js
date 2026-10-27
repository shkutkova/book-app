// Закладка «В мои книги»: запускается на странице фанфика ficbook.net в ТВОЁМ браузере,
// собирает данные со страницы и открывает /add/ficbook в приложении, где их можно
// проверить и сохранить. Сервер приложения сам на ficbook не ходит (ficbook не пускает ботов).
// __BASE__ заменяется на адрес приложения, когда страница /add/ficbook отдаёт закладку.
// Тот же код работает в «Быстрой команде» iPhone (Поделиться → В мои книги): там есть
// функция completion — отдаём ей адрес, а команда сама его открывает.
(() => {
  const go = url => typeof completion === 'function' ? completion(url) : (location.href = url);
  if (!/^https:\/\/ficbook\.net\/readfic\//.test(location.href)) {
    if (typeof completion === 'function') return go('__BASE__/add/ficbook');
    alert('Открой страницу фанфика на ficbook.net и нажми закладку ещё раз');
    return;
  }
  const text = el => el ? el.textContent.replace(/\s+/g, ' ').trim() : '';
  const field = {};  // «Фэндом» -> блок со значением
  document.querySelectorAll('.description .mb-10').forEach(row => {
    const label = row.querySelector('strong');
    if (label) field[text(label).replace(/:$/, '')] = row.querySelector('div');
  });
  const links = el => el ? [...el.querySelectorAll('a')].map(text).filter(Boolean) : [];
  const idFrom = href => (href || '').split('/').filter(Boolean)[1] || null;

  // Авторы и переводчики (беты и гаммы не нужны)
  const people = [...document.querySelectorAll('.fanfic-hat-body section .text-n1')].map(box => {
    const a = box.querySelector('a[href^="/authors/"]');
    const role = text(box.querySelector('.ds-badge')).toLowerCase();
    if (!a) return null;
    if (/перевод/.test(role)) return {name: text(a), id: idFrom(a.getAttribute('href')), role: 'translator'};
    if (/автор/.test(role)) return {name: text(a), id: idFrom(a.getAttribute('href')), role: 'author'};
    return null;
  }).filter(Boolean);

  // «384 страницы, 130 273 слова, 24 части»
  const size = text(field['Размер']);
  const num = re => { const m = size.match(re); return m ? +m[1].replace(/\D/g, '') : null; };

  // «Драко Малфой/Гермиона Грейнджер, ОМП, Гарри Поттер» -> пейринги и персонажи
  const cast = text(field['Пэйринг и персонажи']).split(/,\s*/).filter(Boolean);
  const badge = cls => document.querySelector('.fanfic-badges [class*="' + cls + '"]');
  const series = field['Серия'] && field['Серия'].querySelector('a');
  const direction = document.querySelector('.fanfic-badges .direction');

  const data = {
    url: location.origin + location.pathname,
    title: text(document.querySelector('h1')),
    people,
    // у некоторых работ указана только «Вселенная», без «Фэндома»
    fandoms: links(field['Фэндом']).length ? links(field['Фэндом']) : links(field['Вселенная']),
    pairings: cast.filter(c => c.includes('/')),
    characters: cast.filter(c => !c.includes('/')),
    pages: num(/([\d\s]+)\s+страниц/),
    words: num(/([\d\s]+)\s+слов/),
    parts: num(/([\d\s]+)\s+част/),
    status: text(badge('ds-label-status-')),
    rating: text(badge('ds-label-rating-')),
    direction: direction ? (text(direction) || direction.title.split(' —')[0]) : '',
    translation: !!badge('ds-label-translate'),
    original_url: text(field['Оригинал']),
    original_author: text(field['Автор оригинала']),
    cover: (document.querySelector('.fanfic-hat-cover img') || {}).src || '',
    description: field['Описание'] ? field['Описание'].innerText.trim() : '',
    series: series ? {id: idFrom(series.getAttribute('href')), name: text(series)} : null,
    tags: links(field['Метки']),
  };
  go('__BASE__/add/ficbook#' + encodeURIComponent(JSON.stringify(data)));
})();

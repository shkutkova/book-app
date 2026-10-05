-- =====================================================================
-- Book tracker: структура базы для Supabase (PostgreSQL)
-- Как запустить: Supabase → SQL Editor → вставить весь файл → Run.
-- Файл можно запускать на пустой базе. Повторный запуск упадёт,
-- потому что таблицы уже есть — это нормально.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. КАТАЛОГ: книги, авторы, серии (то, что берём из Hardcover)
--    Здесь лежат ВСЕ книги, о которых знает приложение, в том числе
--    книги серии, которые ты ещё не добавляла к себе.
-- ---------------------------------------------------------------------

create table authors (
    id            bigint generated always as identity primary key,
    hardcover_id  integer unique,          -- пусто, если автор добавлен вручную
    notion_id     text unique,             -- id страницы в Notion (для повторного импорта)
    name          text not null,           -- как в Hardcover: "Rina Kent"
    name_ru       text                     -- свой вариант: "Рина Кент"
);

create table books (
    id             bigint generated always as identity primary key,
    hardcover_id   integer unique,         -- пусто для книг, которых нет в Hardcover
    hardcover_slug text unique,            -- для ссылки на страницу в Hardcover
    notion_id      text unique,            -- id страницы в Notion (для повторного импорта)
    title          text not null,          -- оригинальное название
    title_ru       text,                   -- "Обет обмана"
    description    text,                   -- описание из Hardcover (обычно на английском)
    description_ru text,                   -- описание на русском (Summary из Notion)
    source_url     text,                   -- ссылка, только если книги нет в Hardcover (ficbook и т.п.)
    pages          integer check (pages > 0),
    release_date   date,                   -- нужна для «вышла / выйдет в марте»
    cover_url      text,
    -- Жанры, настроения и предупреждения из Hardcover, как есть:
    -- {"genres": ["Fantasy", ...], "moods": ["Dark", ...], "content_warnings": [...]}
    hardcover_tags jsonb not null default '{}'::jsonb,
    synced_at      timestamptz             -- служебное: когда последний раз брали данные из Hardcover
);

create table book_authors (
    book_id    bigint not null references books(id) on delete cascade,
    author_id  bigint not null references authors(id) on delete restrict,
    primary key (book_id, author_id)
);

create table series (
    id                 bigint generated always as identity primary key,
    hardcover_id       integer unique,
    notion_id          text unique,        -- id страницы в Notion (для повторного импорта)
    name               text not null,      -- "Blood and Ash"
    name_ru            text,               -- "Кровь и пепел"
    description        text,               -- о чём серия: показывается на странице серии
    notes              text,               -- твой комментарий: порядок чтения, «есть ещё третья книга»
    is_abandoned       boolean not null default false,  -- «бросила серию» — единственный ручной статус
    use_my_order       boolean not null default false   -- показывать книги в моём порядке, а не по Hardcover
);

-- Какие книги входят в серию и под какими номерами.
-- Одна книга может быть в нескольких сериях (общая вселенная + подсерия).
create table series_books (
    series_id           bigint not null references series(id) on delete cascade,
    book_id             bigint not null references books(id) on delete cascade,
    official_position   numeric(6,2),      -- официальный номер: 1, 2, 1.5 (из Hardcover или Notion)
    my_position         numeric(6,2),      -- твой порядок; если пусто — берём official_position
    primary key (series_id, book_id)
);


-- ---------------------------------------------------------------------
-- 2. МОЯ БИБЛИОТЕКА: что из каталога лично твоё
--    Книга есть в library → она «твоя» (хочу прочитать / читаю / ...).
--    Книги серии, которых нет в library, показываются как «не добавлена».
-- ---------------------------------------------------------------------

-- Твой короткий список жанров для статистики (как в Notion).
create table my_genres (
    id     bigint generated always as identity primary key,
    name   text not null unique,           -- "Dark Romance", "Fantasy"
    color  text                            -- цвет для диаграмм, например "#d9569a"
);

create type book_status as enum (
    'want_to_read',   -- Хочу прочитать (TBR)
    'reading',        -- Читаю
    'finished',       -- Прочитано
    'paused',         -- На паузе
    'dnf',            -- Брошено
    'skipped'         -- Пропускаю: книга серии, которую не планирую читать
);

create table library (
    book_id      bigint primary key references books(id) on delete cascade,
    status       book_status not null default 'want_to_read',
    -- Оценка 0.5–5 с шагом 0.5 (как звёзды в Notion, плюс половинки)
    rating       numeric(2,1) check (rating between 0.5 and 5 and rating * 2 = floor(rating * 2)),
    is_favorite  boolean not null default false,  -- избранное (🔥 в Notion)
    my_genre_id  bigint references my_genres(id) on delete set null,
    notes        text
);

-- Прочтения. Отдельная таблица, чтобы перечитывания не терялись:
-- одна книга может быть прочитана несколько раз, и каждое прочтение
-- попадает в свой месяц в статистике.
create table reads (
    id           bigint generated always as identity primary key,
    book_id      bigint not null references library(book_id) on delete cascade,
    started_at   date,
    finished_at  date,                     -- пусто, пока книга читается
    check (finished_at is null or started_at is null or finished_at >= started_at)
);


-- ---------------------------------------------------------------------
-- 3. ЗАДЕЛ НА ПОТОМ: «что понравилось» → рекомендации из TBR
--    Таблицы созданы сразу, чтобы потом не переделывать базу.
-- ---------------------------------------------------------------------

create table liked_tags (
    id    bigint generated always as identity primary key,
    name  text not null unique             -- "химия", "приключения", "злодей"
);

create table library_liked_tags (
    book_id  bigint not null references library(book_id) on delete cascade,
    tag_id   bigint not null references liked_tags(id) on delete cascade,
    primary key (book_id, tag_id)
);


-- ---------------------------------------------------------------------
-- 4. ИНДЕКСЫ: чтобы частые выборки работали быстро
-- ---------------------------------------------------------------------

create index on series_books (book_id);
create index on book_authors (author_id);
create index on library (status);
create index on reads (book_id);
create index on reads (finished_at);


-- ---------------------------------------------------------------------
-- 5. ГОТОВЫЕ ВЫБОРКИ (views)
-- ---------------------------------------------------------------------

-- Прогресс по сериям. Статус серии считается сам, руками только «бросила».
create view series_progress as
select
    s.id,
    s.name,
    s.name_ru,
    -- Книги со статусом «пропускаю» не считаются: «5 из 7», а не «5 из 8»
    count(*) filter (where l.status is distinct from 'skipped')         as total_books,
    count(*) filter (where l.status = 'finished')                       as finished_books,
    count(*) filter (where l.status = 'skipped')                        as skipped_books,
    bool_or(l.status = 'reading')                                       as is_reading,
    case
        when s.is_abandoned then 'abandoned'
        when bool_or(l.status = 'reading') then 'in_progress'
        when count(*) filter (where l.status is distinct from 'skipped')
           = count(*) filter (where l.status = 'finished')
         and count(*) filter (where l.status = 'finished') > 0 then 'done'
        when count(*) filter (where l.status = 'finished') > 0 then 'in_progress'
        else 'to_read'
    end                                                                 as status
from series s
join series_books sb on sb.series_id = s.id
left join library l on l.book_id = sb.book_id
group by s.id;

-- Книги серии в правильном порядке: мой порядок, если включён и заполнен,
-- иначе номер из Hardcover. Книги без номера — в конце.
create view series_books_ordered as
select
    sb.series_id,
    sb.book_id,
    sb.official_position,
    sb.my_position,
    case when s.use_my_order and sb.my_position is not null
         then sb.my_position else sb.official_position end as sort_position,
    l.status,
    l.rating,
    l.is_favorite
from series_books sb
join series s on s.id = sb.series_id
left join library l on l.book_id = sb.book_id;


-- ---------------------------------------------------------------------
-- 6. ДОСТУП
--    Supabase открывает таблицы наружу через свой API. Включаем RLS
--    без разрешающих правил: снаружи по публичному ключу никто ничего
--    не прочитает и не изменит. Твой сервер подключается к базе
--    напрямую (строка подключения из .env) и работает как обычно.
-- ---------------------------------------------------------------------

alter table authors            enable row level security;
alter table books              enable row level security;
alter table book_authors       enable row level security;
alter table series             enable row level security;
alter table series_books       enable row level security;
alter table my_genres          enable row level security;
alter table library            enable row level security;
alter table reads              enable row level security;
alter table liked_tags         enable row level security;
alter table library_liked_tags enable row level security;

alter view series_progress      set (security_invoker = true);
alter view series_books_ordered set (security_invoker = true);


-- ---------------------------------------------------------------------
-- 7. СТАРТОВЫЕ ЖАНРЫ (все 8 жанров из твоего Notion; можно поменять)
-- ---------------------------------------------------------------------

insert into my_genres (name, color) values
    ('Dark Romance',  '#d9569a'),
    ('Fantasy',       '#4f86f0'),
    ('Fan Fiction',   '#e3b23c'),
    ('Romance',       '#e8793a'),
    ('Urban Fantasy', '#5046e5'),
    ('Mafia Romance', '#b23a48'),
    ('Dark Fantasy',  '#6b4fa0'),
    ('Dark Academia', '#5cc16a');

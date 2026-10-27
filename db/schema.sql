-- =====================================================================
-- Book tracker: структура базы для Supabase (PostgreSQL)
-- Как запустить: Supabase → SQL Editor → вставить весь файл → Run.
-- Файл — для ПУСТОЙ базы. Если база уже создана старой версией этого
-- файла, запускай не его, а миграции из папки db/migrations по порядку.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 0. ПОЛЬЗОВАТЕЛИ
--    Пока пользователь один, но все «личные» данные уже привязаны
--    к пользователю, чтобы потом можно было пустить других.
--    Когда появится вход (Supabase Auth), id профиля станет равен
--    id пользователя в auth.users: все ссылки на профиль обновятся
--    сами (on update cascade).
-- ---------------------------------------------------------------------

create table profiles (
    id            uuid primary key default gen_random_uuid(),
    display_name  text,
    created_at    timestamptz not null default now()
);


-- ---------------------------------------------------------------------
-- 1. КАТАЛОГ: книги, фанфики, авторы, серии (общие для всех)
--    Здесь лежат ВСЕ книги, о которых знает приложение, в том числе
--    книги серии, которые ты ещё не добавляла к себе.
-- ---------------------------------------------------------------------

create table authors (
    id            bigint generated always as identity primary key,
    hardcover_id  integer unique,          -- пусто, если автор добавлен вручную
    ficbook_id    text unique,             -- id автора на ficbook: /authors/141140 -> "141140"
    notion_id     text unique,             -- id страницы в Notion (для повторного импорта)
    name          text not null,           -- как в Hardcover: "Rina Kent"
    name_ru       text                     -- свой вариант: "Рина Кент"
);

create type book_kind as enum ('book', 'fanfic');

create table books (
    id             bigint generated always as identity primary key,
    kind           book_kind not null default 'book',
    hardcover_id   integer unique,         -- пусто для книг, которых нет в Hardcover
    hardcover_slug text unique,            -- для ссылки на страницу в Hardcover
    ficbook_id     text unique,            -- id фанфика: ficbook.net/readfic/<id>
    notion_id      text unique,            -- id страницы в Notion (для повторного импорта)
    title          text not null,          -- оригинальное название
    title_ru       text,                   -- "Обет обмана"
    description    text,                   -- описание из Hardcover или ficbook
    description_ru text,                   -- описание на русском (Summary из Notion)
    source_url     text,                   -- где читать: ссылка на ficbook и т.п.
    pages          integer check (pages > 0),
    release_date   date,                   -- нужна для «вышла / выйдет в марте»
    cover_url      text,
    -- Жанры, настроения и предупреждения из Hardcover, как есть:
    -- {"genres": ["Fantasy", ...], "moods": ["Dark", ...], "content_warnings": [...]}
    hardcover_tags jsonb not null default '{}'::jsonb,
    synced_at      timestamptz,            -- служебное: когда последний раз брали данные из Hardcover
    -- Только для фанфиков:
    fandoms        text[] not null default '{}',   -- {"Гарри Поттер (Harry Potter)"}
    pairings       text[] not null default '{}',   -- {"Гермиона Грейнджер/Драко Малфой"}
    work_status    text check (work_status in ('in_progress', 'finished', 'frozen')),
    words          integer check (words > 0),
    parts          integer check (parts > 0),
    -- Остальное с ficbook, как есть: направленность, рейтинг, метки, оригинал перевода:
    -- {"direction": "Гет", "rating": "NC-17", "tags": [...], "characters": [...],
    --  "translation": true, "original_url": "...", "original_author": "..."}
    ficbook_meta   jsonb not null default '{}'::jsonb
);

create table book_authors (
    book_id    bigint not null references books(id) on delete cascade,
    author_id  bigint not null references authors(id) on delete restrict,
    role       text not null default 'author' check (role in ('author', 'translator')),
    primary key (book_id, author_id)
);

create table series (
    id                 bigint generated always as identity primary key,
    hardcover_id       integer unique,
    ficbook_id         text unique,        -- серия (цикл) на ficbook: /series/18329 -> "18329"
    notion_id          text unique,        -- id страницы в Notion (для повторного импорта)
    name               text not null,      -- "Blood and Ash"
    name_ru            text,               -- "Кровь и пепел"
    description        text,               -- о чём серия: показывается на странице серии
    is_completed       boolean             -- серия завершена (из Hardcover); пусто — неизвестно
);

-- Какие книги входят в серию и под какими номерами.
-- Одна книга может быть в нескольких сериях (общая вселенная + подсерия).
create table series_books (
    series_id           bigint not null references series(id) on delete cascade,
    book_id             bigint not null references books(id) on delete cascade,
    official_position   numeric(6,2),      -- официальный номер: 1, 2, 1.5 (из Hardcover или Notion)
    primary key (series_id, book_id)
);


-- ---------------------------------------------------------------------
-- 2. МОЯ БИБЛИОТЕКА: что из каталога лично твоё (у каждого пользователя своё)
--    Книга есть в library → она «твоя» (хочу прочитать / читаю / ...).
--    Книги серии, которых нет в library, показываются как «не добавлена».
-- ---------------------------------------------------------------------

-- Твой короткий список жанров для статистики (как в Notion).
create table my_genres (
    id       bigint generated always as identity primary key,
    user_id  uuid not null references profiles(id) on delete cascade on update cascade,
    name     text not null,                -- "Dark Romance", "Fantasy"
    color    text,                         -- цвет для диаграмм, например "#d9569a"
    unique (user_id, name)
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
    user_id      uuid not null references profiles(id) on delete cascade on update cascade,
    book_id      bigint not null references books(id) on delete cascade,
    status       book_status not null default 'want_to_read',
    -- Оценка 0.5–5 с шагом 0.5 (как звёзды в Notion, плюс половинки)
    rating       numeric(2,1) check (rating between 0.5 and 5 and rating * 2 = floor(rating * 2)),
    is_favorite  boolean not null default false,  -- избранное (🔥 в Notion)
    my_genre_id  bigint references my_genres(id) on delete set null,
    notes        text,
    primary key (user_id, book_id)
);

-- Прочтения. Отдельная таблица, чтобы перечитывания не терялись:
-- одна книга может быть прочитана несколько раз, и каждое прочтение
-- попадает в свой месяц в статистике.
create table reads (
    id           bigint generated always as identity primary key,
    user_id      uuid not null,
    book_id      bigint not null,
    started_at   date,
    finished_at  date,                     -- пусто, пока книга читается
    check (finished_at is null or started_at is null or finished_at >= started_at),
    foreign key (user_id, book_id) references library(user_id, book_id)
        on delete cascade on update cascade
);

-- Твоё отношение к серии: «бросила», свой порядок книг.
-- Строки нет — значит, ничего не менялось (не брошена, порядок официальный).
create table user_series (
    user_id       uuid not null references profiles(id) on delete cascade on update cascade,
    series_id     bigint not null references series(id) on delete cascade,
    is_abandoned  boolean not null default false,  -- «бросила серию» — единственный ручной статус
    use_my_order  boolean not null default false,  -- показывать книги в моём порядке, а не официальном
    primary key (user_id, series_id)
);

-- Свой номер книги в серии. Строки нет — берётся официальный номер.
create table user_series_books (
    user_id      uuid not null references profiles(id) on delete cascade on update cascade,
    series_id    bigint not null,
    book_id      bigint not null,
    my_position  numeric(6,2) not null,
    primary key (user_id, series_id, book_id),
    foreign key (series_id, book_id) references series_books(series_id, book_id) on delete cascade
);


-- ---------------------------------------------------------------------
-- 3. ЗАДЕЛ НА ПОТОМ: «что понравилось» → рекомендации из TBR
--    Таблицы созданы сразу, чтобы потом не переделывать базу.
-- ---------------------------------------------------------------------

create table liked_tags (
    id       bigint generated always as identity primary key,
    user_id  uuid not null references profiles(id) on delete cascade on update cascade,
    name     text not null,                -- "химия", "приключения", "злодей"
    unique (user_id, name)
);

create table library_liked_tags (
    user_id  uuid not null,
    book_id  bigint not null,
    tag_id   bigint not null references liked_tags(id) on delete cascade,
    primary key (user_id, book_id, tag_id),
    foreign key (user_id, book_id) references library(user_id, book_id)
        on delete cascade on update cascade
);


-- ---------------------------------------------------------------------
-- 4. ИНДЕКСЫ: чтобы частые выборки работали быстро
-- ---------------------------------------------------------------------

create index on series_books (book_id);
create index on book_authors (author_id);
create index on library (book_id);
create index on library (user_id, status);
create index on reads (user_id, book_id);
create index on reads (user_id, finished_at);


-- ---------------------------------------------------------------------
-- 5. ГОТОВЫЕ ВЫБОРКИ (views)
--    В каждой есть user_id: выбирать всегда с where user_id = ...
-- ---------------------------------------------------------------------

-- Прогресс по сериям. Статус серии считается сам, руками только «бросила».
-- Основная книга — с целым номером (1, 2, 3) или без номера; дробный номер (1.5) —
-- дополнительная (повесть, рассказ): в «X из Y» не входит.
create view series_progress as
select
    p.id                                                                       as user_id,
    s.id,
    s.name,
    s.name_ru,
    count(l.book_id)                                                           as my_books,
    -- «Пропускаю» не считается: «5 из 7», а не «5 из 8». Дополнительные — тоже.
    count(*) filter (where x.is_main and l.status is distinct from 'skipped')  as total_books,
    count(*) filter (where x.is_main and l.status = 'finished')                as finished_books,
    count(*) filter (where x.is_main and l.status = 'skipped')                 as skipped_books,
    count(*) filter (where not x.is_main)                                      as extra_books,
    coalesce(bool_or(l.status = 'reading'), false)                             as is_reading,
    case
        when coalesce(us.is_abandoned, false) then 'abandoned'
        when bool_or(l.status = 'reading') then 'in_progress'
        when count(*) filter (where x.is_main and l.status is distinct from 'skipped')
           = count(*) filter (where x.is_main and l.status = 'finished')
         and count(*) filter (where x.is_main and l.status = 'finished') > 0 then 'done'
        when count(*) filter (where l.status = 'finished') > 0 then 'in_progress'
        else 'to_read'
    end                                                                        as status
from profiles p
cross join series s
join series_books sb on sb.series_id = s.id
cross join lateral (select sb.official_position is null
                        or sb.official_position = trunc(sb.official_position) as is_main) x
left join library l on l.book_id = sb.book_id and l.user_id = p.id
left join user_series us on us.series_id = s.id and us.user_id = p.id
group by p.id, s.id, us.is_abandoned;

-- Книги серии в правильном порядке: мой порядок, если включён и заполнен,
-- иначе официальный номер. Книги без номера — в конце.
create view series_books_ordered as
select
    p.id as user_id,
    sb.series_id,
    sb.book_id,
    sb.official_position,
    usb.my_position,
    case when coalesce(us.use_my_order, false) and usb.my_position is not null
         then usb.my_position else sb.official_position end as sort_position,
    l.status,
    l.rating,
    l.is_favorite
from profiles p
cross join series_books sb
left join user_series us
       on us.user_id = p.id and us.series_id = sb.series_id
left join user_series_books usb
       on usb.user_id = p.id and usb.series_id = sb.series_id and usb.book_id = sb.book_id
left join library l on l.user_id = p.id and l.book_id = sb.book_id;


-- ---------------------------------------------------------------------
-- 6. ДОСТУП
--    Supabase открывает таблицы наружу через свой API. Включаем RLS
--    без разрешающих правил: снаружи по публичному ключу никто ничего
--    не прочитает и не изменит. Твой сервер подключается к базе
--    напрямую (строка подключения из .env) и работает как обычно.
-- ---------------------------------------------------------------------

alter table profiles           enable row level security;
alter table authors            enable row level security;
alter table books              enable row level security;
alter table book_authors       enable row level security;
alter table series             enable row level security;
alter table series_books       enable row level security;
alter table my_genres          enable row level security;
alter table library            enable row level security;
alter table reads              enable row level security;
alter table user_series        enable row level security;
alter table user_series_books  enable row level security;
alter table liked_tags         enable row level security;
alter table library_liked_tags enable row level security;

alter view series_progress      set (security_invoker = true);
alter view series_books_ordered set (security_invoker = true);


-- ---------------------------------------------------------------------
-- 7. ПЕРВЫЙ ПОЛЬЗОВАТЕЛЬ И СТАРТОВЫЕ ЖАНРЫ (8 жанров из твоего Notion)
-- ---------------------------------------------------------------------

with me as (insert into profiles (display_name) values ('Я') returning id)
insert into my_genres (user_id, name, color)
select me.id, g.name, g.color
from me, (values
    ('Dark Romance',  '#d9569a'),
    ('Fantasy',       '#4f86f0'),
    ('Fan Fiction',   '#e3b23c'),
    ('Romance',       '#e8793a'),
    ('Urban Fantasy', '#5046e5'),
    ('Mafia Romance', '#b23a48'),
    ('Dark Fantasy',  '#6b4fa0'),
    ('Dark Academia', '#5cc16a')
) as g(name, color);

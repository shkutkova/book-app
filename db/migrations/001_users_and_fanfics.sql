-- =====================================================================
-- Миграция 001: привязка личных данных к пользователю + поля для фанфиков.
-- Для базы, созданной СТАРОЙ версией db/schema.sql (до этой миграции).
--
-- Как запустить: Supabase → SQL Editor → вставить весь файл → Run.
-- Всё выполняется одной транзакцией: если что-то упадёт, база останется как была.
--
-- Ничего не удаляет. Старые колонки series.notes / is_abandoned / use_my_order
-- и series_books.my_position копируются в новые таблицы, но остаются на месте —
-- их убирает отдельная миграция 002, когда проверишь, что всё перенеслось.
-- =====================================================================

begin;

-- ---------------------------------------------------------------- профиль

create table profiles (
    id            uuid primary key default gen_random_uuid(),
    display_name  text,
    created_at    timestamptz not null default now()
);
insert into profiles (display_name) values ('Я');



-- ---------------------------------------------------------------- старые связи снимаем
-- (их заменят связи с user_id ниже)

drop view series_progress;
drop view series_books_ordered;
alter table reads              drop constraint reads_book_id_fkey;
alter table library_liked_tags drop constraint library_liked_tags_book_id_fkey;
alter table library_liked_tags drop constraint library_liked_tags_pkey;


-- ---------------------------------------------------------------- жанры и теги — свои у каждого

alter table my_genres add column user_id uuid references profiles(id) on delete cascade on update cascade;
update my_genres set user_id = (select id from profiles);
alter table my_genres alter column user_id set not null;
alter table my_genres drop constraint my_genres_name_key;
alter table my_genres add unique (user_id, name);

alter table liked_tags add column user_id uuid references profiles(id) on delete cascade on update cascade;
update liked_tags set user_id = (select id from profiles);
alter table liked_tags alter column user_id set not null;
alter table liked_tags drop constraint liked_tags_name_key;
alter table liked_tags add unique (user_id, name);


-- ---------------------------------------------------------------- библиотека

alter table library add column user_id uuid references profiles(id) on delete cascade on update cascade;
update library set user_id = (select id from profiles);
alter table library alter column user_id set not null;
alter table library drop constraint library_pkey;
alter table library add primary key (user_id, book_id);

alter table reads add column user_id uuid;
update reads set user_id = (select id from profiles);
alter table reads alter column user_id set not null;
alter table reads add foreign key (user_id, book_id) references library(user_id, book_id)
    on delete cascade on update cascade;

alter table library_liked_tags add column user_id uuid;
update library_liked_tags set user_id = (select id from profiles);
alter table library_liked_tags alter column user_id set not null;
alter table library_liked_tags add primary key (user_id, book_id, tag_id);
alter table library_liked_tags add foreign key (user_id, book_id) references library(user_id, book_id)
    on delete cascade on update cascade;


-- ---------------------------------------------------------------- серии: личное — в отдельные таблицы

create table user_series (
    user_id       uuid not null references profiles(id) on delete cascade on update cascade,
    series_id     bigint not null references series(id) on delete cascade,
    notes         text,
    is_abandoned  boolean not null default false,
    use_my_order  boolean not null default false,
    primary key (user_id, series_id)
);
insert into user_series (user_id, series_id, notes, is_abandoned, use_my_order)
select (select id from profiles), id, notes, is_abandoned, use_my_order
from series
where notes is not null or is_abandoned or use_my_order;

create table user_series_books (
    user_id      uuid not null references profiles(id) on delete cascade on update cascade,
    series_id    bigint not null,
    book_id      bigint not null,
    my_position  numeric(6,2) not null,
    primary key (user_id, series_id, book_id),
    foreign key (series_id, book_id) references series_books(series_id, book_id) on delete cascade
);
insert into user_series_books (user_id, series_id, book_id, my_position)
select (select id from profiles), series_id, book_id, my_position
from series_books
where my_position is not null;


-- ---------------------------------------------------------------- фанфики

create type book_kind as enum ('book', 'fanfic');

alter table books
    add column kind         book_kind not null default 'book',
    add column ficbook_id   text unique,
    add column fandoms      text[] not null default '{}',
    add column pairings     text[] not null default '{}',
    add column work_status  text check (work_status in ('in_progress', 'finished', 'frozen')),
    add column words        integer check (words > 0),
    add column parts        integer check (parts > 0),
    add column ficbook_meta jsonb not null default '{}'::jsonb;

alter table authors add column ficbook_id text unique;
alter table series  add column ficbook_id text unique;
alter table book_authors add column role text not null default 'author'
    check (role in ('author', 'translator'));

-- Фанфики из Notion: ссылка на ficbook или жанр Fan Fiction
update books b set kind = 'fanfic'
where b.source_url ilike '%ficbook.net/%'
   or exists (select 1 from library l join my_genres g on g.id = l.my_genre_id
              where l.book_id = b.id and g.name = 'Fan Fiction');
-- id фанфика из ссылки: https://ficbook.net/readfic/<id>... (если ссылка ровно на фанфик)
update books b set ficbook_id = m.id
from (select id as book_id, substring(source_url from 'ficbook\.net/readfic/([0-9A-Za-z-]+)') as id
      from books) m
where m.book_id = b.id and m.id is not null
  -- одна и та же ссылка у двух книг — не трогаем, чтобы не упасть на unique
  and (select count(*) from books x
       where substring(x.source_url from 'ficbook\.net/readfic/([0-9A-Za-z-]+)') = m.id) = 1;


-- ---------------------------------------------------------------- индексы

drop index if exists library_status_idx;
drop index if exists reads_book_id_idx;
drop index if exists reads_finished_at_idx;
create index on library (book_id);
create index on library (user_id, status);
create index on reads (user_id, book_id);
create index on reads (user_id, finished_at);


-- ---------------------------------------------------------------- готовые выборки — теперь с user_id

create view series_progress as
select
    p.id                                                                as user_id,
    s.id,
    s.name,
    s.name_ru,
    count(l.book_id)                                                    as my_books,
    count(*) filter (where l.status is distinct from 'skipped')         as total_books,
    count(*) filter (where l.status = 'finished')                       as finished_books,
    count(*) filter (where l.status = 'skipped')                        as skipped_books,
    coalesce(bool_or(l.status = 'reading'), false)                      as is_reading,
    case
        when coalesce(us.is_abandoned, false) then 'abandoned'
        when bool_or(l.status = 'reading') then 'in_progress'
        when count(*) filter (where l.status is distinct from 'skipped')
           = count(*) filter (where l.status = 'finished')
         and count(*) filter (where l.status = 'finished') > 0 then 'done'
        when count(*) filter (where l.status = 'finished') > 0 then 'in_progress'
        else 'to_read'
    end                                                                 as status
from profiles p
cross join series s
join series_books sb on sb.series_id = s.id
left join library l on l.book_id = sb.book_id and l.user_id = p.id
left join user_series us on us.series_id = s.id and us.user_id = p.id
group by p.id, s.id, us.is_abandoned;

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


-- ---------------------------------------------------------------- доступ

alter table profiles          enable row level security;
alter table user_series       enable row level security;
alter table user_series_books enable row level security;
alter view series_progress      set (security_invoker = true);
alter view series_books_ordered set (security_invoker = true);

commit;

-- Проверка после запуска (должно совпасть с тем, что было до):
--   select count(*) from library;            -- столько же книг, сколько было
--   select count(*) from user_series;        -- серии с заметками / «бросила» / своим порядком
--   select count(*) from books where kind = 'fanfic';

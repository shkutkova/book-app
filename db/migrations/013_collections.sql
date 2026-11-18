-- =====================================================================
-- Миграция 013: свои подборки (как сборники на ficbook / папки в Fable).
-- Подборка — название и цвет; в ней книги и фанфики из своей библиотеки.
-- Убрала книгу из библиотеки — из подборок она уходит сама (каскад).
-- Ничего не удаляет. Как запустить: Supabase → SQL Editor → весь файл → Run.
-- =====================================================================

create table if not exists collections (
    id          bigint generated always as identity primary key,
    user_id     uuid not null references profiles(id) on delete cascade on update cascade,
    name        text not null check (length(trim(name)) between 1 and 60),
    color       text not null default 'lilac'
                check (color in ('lilac', 'butter', 'peach', 'mint', 'sky', 'pink')),
    created_at  timestamptz not null default now(),
    unique (user_id, name)
);

create table if not exists collection_books (
    collection_id bigint not null references collections(id) on delete cascade,
    user_id       uuid   not null,
    book_id       bigint not null,
    added_at      timestamptz not null default now(),
    primary key (collection_id, book_id),
    foreign key (user_id, book_id) references library(user_id, book_id)
        on delete cascade on update cascade
);
create index if not exists collection_books_book on collection_books (user_id, book_id);

alter table collections enable row level security;
alter table collection_books enable row level security;

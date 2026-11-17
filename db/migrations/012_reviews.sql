-- =====================================================================
-- Миграция 012: отзыв после прочтения — «о чём книга» для себя и опросник
-- (настроение, темп, что движет историей, что понравилось, перечитала бы).
-- Тропы, которые понравились, — в уже существующих liked_tags / library_liked_tags.
-- Ничего не удаляет. Как запустить: Supabase → SQL Editor → весь файл → Run.
-- =====================================================================

create table if not exists reviews (
    user_id     uuid   not null,
    book_id     bigint not null,
    summary     text,                                  -- «о чём была», коротко для себя
    is_spoiler  boolean not null default false,        -- текст скрыт, пока не нажмёшь
    moods       text[] not null default '{}',          -- ключи как у Hardcover: dark, tense, …
    pace        text check (pace in ('slow', 'medium', 'fast')),
    driven      text check (driven in ('plot', 'mix', 'character')),
    liked       text[] not null default '{}',          -- plot, characters, world, romance, …
    reread      text check (reread in ('yes', 'maybe', 'no')),
    updated_at  timestamptz not null default now(),
    primary key (user_id, book_id),
    foreign key (user_id, book_id) references library(user_id, book_id)
        on delete cascade on update cascade
);

alter table reviews enable row level security;

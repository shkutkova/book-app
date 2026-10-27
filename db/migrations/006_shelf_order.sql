-- =====================================================================
-- Миграция 006: свой порядок на полке главной (перетаскивание корешков).
-- Ничего не удаляет. Как запустить: Supabase → SQL Editor → весь файл → Run.
-- =====================================================================

-- shelf — полка ('fav', 'reading', 'want'); item — 'b<id книги>' или 's<id серии>'.
-- Строки нет — место по умолчанию (по названию, после расставленных).
create table if not exists shelf_order (
    user_id  uuid not null references profiles(id) on delete cascade on update cascade,
    shelf    text not null check (shelf in ('fav', 'reading', 'want')),
    item     text not null,
    pos      int  not null,
    primary key (user_id, shelf, item)
);

-- Как у остальных таблиц: снаружи через API Supabase не читается
alter table shelf_order enable row level security;

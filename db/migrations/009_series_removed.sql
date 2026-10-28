-- =====================================================================
-- Миграция 009: книги, убранные из серии вручную (лишние издания из Hardcover).
-- «Обновить из Hardcover» их больше не добавляет. Ничего не удаляет.
-- Как запустить: Supabase → SQL Editor → весь файл → Run.
-- =====================================================================

create table if not exists series_removed (
    series_id     bigint not null references series(id) on delete cascade,
    hardcover_id  int    not null,   -- id книги в Hardcover
    primary key (series_id, hardcover_id)
);

alter table series_removed enable row level security;

-- =====================================================================
-- Проверка базы перед миграцией 001. ТОЛЬКО ЧТЕНИЕ: ничего не меняет.
-- Как запустить: Supabase → SQL Editor → вставить весь файл → Run.
-- Результат — одна ячейка report (JSON): скопируй её целиком.
-- =====================================================================

select json_build_object(
    'tables', (select json_agg(table_name::text order by table_name)
               from information_schema.tables where table_schema = 'public'),
    'columns', (select json_object_agg(table_name, cols) from (
                  select table_name, json_agg(column_name::text order by ordinal_position) as cols
                  from information_schema.columns where table_schema = 'public'
                  group by table_name) c),
    'constraints', (select json_agg(conrelid::regclass::text || '.' || conname order by 1)
                    from pg_constraint c join pg_namespace n on n.oid = c.connamespace
                    where n.nspname = 'public' and contype in ('p', 'f', 'u')),
    'indexes', (select json_agg(indexname::text order by indexname)
                from pg_indexes where schemaname = 'public'),
    'enum_types', (select json_agg(typname::text)
                   from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'public' and t.typtype = 'e'),
    -- число строк в каждой таблице
    'counts', (select json_object_agg(table_name,
                 (xpath('/row/c/text()', query_to_xml(
                     format('select count(*) as c from public.%I', table_name), false, true, '')))[1]::text::int)
               from information_schema.tables
               where table_schema = 'public' and table_type = 'BASE TABLE'),
    -- личные поля серий, которые миграция переносит в user_series / user_series_books
    'series_personal', (select json_build_object(
                          'notes', count(*) filter (where to_jsonb(s) ->> 'notes' is not null),
                          'abandoned', count(*) filter (where (to_jsonb(s) ->> 'is_abandoned')::boolean),
                          'my_order', count(*) filter (where (to_jsonb(s) ->> 'use_my_order')::boolean))
                        from series s),
    'my_position_filled', (select count(*) filter (where to_jsonb(sb) ->> 'my_position' is not null)
                           from series_books sb),
    -- что станет фанфиками
    'ficbook_links', (select json_build_object(
                        'rows', count(*),
                        'distinct_ids', count(distinct substring(source_url from 'ficbook\.net/readfic/([0-9A-Za-z-]+)')))
                      from books where source_url ilike '%ficbook.net/%'),
    'source_domains', (select json_object_agg(coalesce(d, '?'), n) from (
                         select substring(source_url from '://([^/]+)') as d, count(*) as n
                         from books where source_url is not null group by 1) x),
    'fan_fiction_genre_books', (select count(*) from library l join my_genres g on g.id = l.my_genre_id
                                where g.name = 'Fan Fiction')
) as report;

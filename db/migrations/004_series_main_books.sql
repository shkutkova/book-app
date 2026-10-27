-- =====================================================================
-- Миграция 004: основные и дополнительные книги серии.
-- Основная книга — с целым номером (1, 2, 3) или без номера.
-- Дополнительная — с дробным (1.5, 0.5): повести, рассказы. В прогресс
-- «X из Y» они не входят, на странице серии показываются отдельно.
-- Плюс отметка «серия завершена» (из Hardcover).
-- Ничего не удаляет. Как запустить: Supabase → SQL Editor → весь файл → Run.
-- =====================================================================

begin;

alter table series add column is_completed boolean;   -- из Hardcover; пусто — неизвестно

drop view series_progress;

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

alter view series_progress set (security_invoker = true);

commit;

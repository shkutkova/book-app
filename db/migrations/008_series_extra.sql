-- =====================================================================
-- Миграция 008: свой выбор «основная / дополнительная» книга серии.
-- Раньше блок «Дополнительно» определялся только официальным номером (1.5 — доп.).
-- Теперь любую книгу можно перенести в «Дополнительно» (лишние издания из Hardcover)
-- или вернуть в основные (например, приквел 0.5 — первым в своём порядке).
-- user_series_books.is_extra: пусто — по официальному номеру, true — доп., false — основная.
-- Ничего не удаляет. Как запустить: Supabase → SQL Editor → весь файл → Run.
-- =====================================================================

begin;

alter table user_series_books alter column my_position drop not null;
alter table user_series_books add column if not exists is_extra boolean;

-- Тот же вид, в конце новая колонка is_main
create or replace view series_books_ordered as
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
    l.is_favorite,
    coalesce(not usb.is_extra,
             sb.official_position is null or sb.official_position = trunc(sb.official_position)) as is_main
from profiles p
cross join series_books sb
left join user_series us
       on us.user_id = p.id and us.series_id = sb.series_id
left join user_series_books usb
       on usb.user_id = p.id and usb.series_id = sb.series_id and usb.book_id = sb.book_id
left join library l on l.user_id = p.id and l.book_id = sb.book_id;

-- Прогресс: основная книга — с учётом своего выбора
create or replace view series_progress as
select
    p.id                                                                       as user_id,
    s.id,
    s.name,
    s.name_ru,
    count(l.book_id)                                                           as my_books,
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
left join user_series_books usb
       on usb.user_id = p.id and usb.series_id = sb.series_id and usb.book_id = sb.book_id
cross join lateral (select coalesce(not usb.is_extra,
                                    sb.official_position is null
                                    or sb.official_position = trunc(sb.official_position)) as is_main) x
left join library l on l.book_id = sb.book_id and l.user_id = p.id
left join user_series us on us.series_id = s.id and us.user_id = p.id
group by p.id, s.id, us.is_abandoned;

-- create or replace сбрасывает настройки вида — возвращаем
alter view series_progress      set (security_invoker = true);
alter view series_books_ordered set (security_invoker = true);

commit;

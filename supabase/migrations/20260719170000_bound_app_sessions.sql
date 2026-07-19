-- Bound durable sessions even under concurrent login/logout abuse.
with device_duplicates as (
  select
    id,
    row_number() over (
      partition by user_id, user_agent, request_ip_hash
      order by last_seen_at desc, created_at desc, id desc
    ) as duplicate_rank
  from public.app_sessions
)
delete from public.app_sessions as sessions
using device_duplicates
where sessions.id = device_duplicates.id
  and device_duplicates.duplicate_rank > 1;

with excess_sessions as (
  select
    id,
    row_number() over (
      partition by user_id
      order by last_seen_at desc, created_at desc, id desc
    ) as session_rank
  from public.app_sessions
)
delete from public.app_sessions as sessions
using excess_sessions
where sessions.id = excess_sessions.id
  and excess_sessions.session_rank > 10;

create unique index if not exists app_sessions_user_device_uidx
on public.app_sessions (user_id, user_agent, request_ip_hash);

create or replace function public.bound_app_session_rows()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
declare
  reusable_id uuid;
begin
  perform pg_advisory_xact_lock(new.user_id);

  select id
  into reusable_id
  from public.app_sessions
  where user_id = new.user_id
    and user_agent = new.user_agent
    and request_ip_hash = new.request_ip_hash
  order by last_seen_at desc, created_at desc, id desc
  limit 1
  for update;

  if reusable_id is not null then
    update public.app_sessions
    set token_hash = new.token_hash,
        created_at = new.created_at,
        last_seen_at = new.last_seen_at,
        revoked_at = null
    where id = reusable_id;
    return null;
  end if;

  if (
    select count(*)
    from public.app_sessions
    where user_id = new.user_id
  ) >= 10 then
    select id
    into reusable_id
    from public.app_sessions
    where user_id = new.user_id
    order by created_at asc, id asc
    limit 1
    for update;

    update public.app_sessions
    set token_hash = new.token_hash,
        user_agent = new.user_agent,
        request_ip_hash = new.request_ip_hash,
        created_at = new.created_at,
        last_seen_at = new.last_seen_at,
        revoked_at = null
    where id = reusable_id;
    return null;
  end if;

  return new;
end;
$$;

drop trigger if exists bound_app_sessions_per_user on public.app_sessions;
create trigger bound_app_sessions_per_user
before insert on public.app_sessions
for each row
execute function public.bound_app_session_rows();

notify pgrst, 'reload schema';

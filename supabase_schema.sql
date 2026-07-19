-- Re-Life Supabase schema
-- Primary tables:
--   app_users      -> user profiles and credentials
--   app_sessions   -> opaque server-side user sessions
--   scan_records   -> scanned waste records
--   auth_codes     -> verification / reset codes
--   news_cache     -> cached news payloads

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.app_users (
  id bigint generated always as identity primary key,
  public_id text not null unique default ('usr_' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 12)),
  display_name text not null unique,
  email text unique,
  password_hash text not null,
  photo_url text,
  spent_points integer not null default 0 check (spent_points >= 0),
  earned_points integer not null default 0 check (earned_points >= 0),
  claimed_coupons jsonb not null default '[]'::jsonb,
  email_verified boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists set_app_users_updated_at on public.app_users;
create trigger set_app_users_updated_at
before update on public.app_users
for each row
execute function public.set_updated_at();

create index if not exists app_users_created_at_idx on public.app_users (created_at desc);

create table if not exists public.app_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id bigint not null references public.app_users(id) on delete cascade,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  user_agent text not null default '' check (char_length(user_agent) <= 256),
  request_ip_hash text not null default '' check (char_length(request_ip_hash) <= 64) check (request_ip_hash = '' or request_ip_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  revoked_at timestamptz
);
create index if not exists app_sessions_user_id_idx on public.app_sessions (user_id);
create index if not exists app_sessions_last_seen_idx on public.app_sessions (last_seen_at);

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

comment on table public.app_sessions is 'Opaque server-side sessions for the custom app_users account system.';
alter table public.app_sessions enable row level security;
revoke all on table public.app_sessions from anon, authenticated;
grant select, insert, update, delete on table public.app_sessions to service_role;

create table if not exists public.scan_records (
  id bigint generated always as identity primary key,
  user_id bigint not null references public.app_users(id) on delete cascade,
  mode text not null check (mode in ('dispose', 'purchase')),
  name text not null,
  description text not null default '',
  image_url text,
  dealt_with_method text,
  eco_rate smallint not null default 3 check (eco_rate between 0 and 5),
  recycle_rate smallint not null default 4 check (recycle_rate between 0 and 5),
  overall_score smallint not null default 0 check (overall_score between 0 and 100),
  material text,
  grade text,
  brand text,
  category text,
  weighted_scores jsonb not null default '{}'::jsonb,
  schema_id text not null,
  alternative jsonb,
  precaution text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists set_scan_records_updated_at on public.scan_records;
create trigger set_scan_records_updated_at
before update on public.scan_records
for each row
execute function public.set_updated_at();

create index if not exists scan_records_user_id_created_at_idx on public.scan_records (user_id, created_at desc);
create index if not exists scan_records_schema_id_idx on public.scan_records (schema_id);
create index if not exists scan_records_mode_idx on public.scan_records (mode);

create table if not exists public.auth_codes (
  id bigint generated always as identity primary key,
  purpose text not null check (purpose in ('verify', 'reset')),
  email text not null,
  user_id bigint references public.app_users(id) on delete cascade,
  code_hash text not null,
  expires_at timestamptz not null,
  attempts integer not null default 0 check (attempts between 0 and 5),
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (purpose, email)
);

alter table public.auth_codes
drop constraint if exists auth_codes_attempts_check;

update public.auth_codes
set attempts = 5,
    consumed_at = coalesce(consumed_at, now())
where attempts > 5;

alter table public.auth_codes
add constraint auth_codes_attempts_check
check (attempts between 0 and 5);

drop trigger if exists set_auth_codes_updated_at on public.auth_codes;
create trigger set_auth_codes_updated_at
before update on public.auth_codes
for each row
execute function public.set_updated_at();

create index if not exists auth_codes_email_idx on public.auth_codes (email);
create index if not exists auth_codes_expires_at_idx on public.auth_codes (expires_at);
create index if not exists auth_codes_active_lookup_idx
on public.auth_codes (purpose, email, expires_at)
where consumed_at is null;

create table if not exists public.news_cache (
  cache_key text primary key,
  data jsonb not null,
  fetched_at timestamptz not null default now()
);

create index if not exists news_cache_fetched_at_idx on public.news_cache (fetched_at desc);

comment on table public.app_users is 'Re-Life user profiles and authentication records.';
comment on table public.scan_records is 'Re-Life waste scan history linked to users.';
comment on table public.auth_codes is 'Email verification and password reset codes.';
comment on table public.news_cache is 'Cached news payloads for the home feed.';

insert into storage.buckets (id, name, public)
values ('scan-images', 'scan-images', true)
on conflict (id) do update
set public = excluded.public;

drop policy if exists "service_role can manage scan images" on storage.objects;
create policy "service_role can manage scan images"
on storage.objects
for all
to service_role
using (bucket_id = 'scan-images')
with check (bucket_id = 'scan-images');

notify pgrst, 'reload schema';

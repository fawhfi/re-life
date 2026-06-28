-- Re-Life Supabase schema
-- Primary tables:
--   app_users      -> user profiles and credentials
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
  attempts integer not null default 0 check (attempts >= 0),
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (purpose, email)
);

drop trigger if exists set_auth_codes_updated_at on public.auth_codes;
create trigger set_auth_codes_updated_at
before update on public.auth_codes
for each row
execute function public.set_updated_at();

create index if not exists auth_codes_email_idx on public.auth_codes (email);
create index if not exists auth_codes_expires_at_idx on public.auth_codes (expires_at);

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

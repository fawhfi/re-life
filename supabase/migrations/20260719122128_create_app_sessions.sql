-- Durable server-side sessions required by /api/auth/login.
create extension if not exists pgcrypto;

create table if not exists public.app_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id bigint not null references public.app_users(id) on delete cascade,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  user_agent text not null default '' check (char_length(user_agent) <= 256),
  request_ip_hash text not null default ''
    check (char_length(request_ip_hash) <= 64)
    check (request_ip_hash = '' or request_ip_hash ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  revoked_at timestamptz
);

create index if not exists app_sessions_user_id_idx
on public.app_sessions (user_id);

create index if not exists app_sessions_last_seen_idx
on public.app_sessions (last_seen_at);

comment on table public.app_sessions is
  'Opaque server-side sessions for the custom app_users account system.';

alter table public.app_sessions enable row level security;
revoke all on table public.app_sessions from anon, authenticated;
grant select, insert, update, delete on table public.app_sessions to service_role;

notify pgrst, 'reload schema';

-- Durable, account-scoped ReAgent history for cross-device continuity.
create table if not exists public.agent_conversations (
  id text primary key
    check (id ~ '^[A-Za-z0-9_-]{24,64}$'),
  user_id bigint not null references public.app_users(id) on delete cascade,
  language text not null default 'en'
    check (language in ('en', 'zh_simplified', 'zh_traditional')),
  title text not null default 'New chat'
    check (char_length(title) <= 80),
  messages jsonb not null default '[]'::jsonb
    check (jsonb_typeof(messages) = 'array')
    check (jsonb_array_length(messages) <= 100)
    check (pg_column_size(messages) <= 2097152),
  session_items jsonb not null default '[]'::jsonb
    check (jsonb_typeof(session_items) = 'array')
    check (jsonb_array_length(session_items) <= 200)
    check (pg_column_size(session_items) <= 4194304),
  pending_state jsonb
    check (pending_state is null or jsonb_typeof(pending_state) = 'object')
    check (pending_state is null or pg_column_size(pending_state) <= 2097152),
  pending_action text not null default ''
    check (char_length(pending_action) <= 64),
  pending_request_id text not null default ''
    check (char_length(pending_request_id) <= 256),
  consent_granted boolean not null default false,
  created_at timestamptz not null default now(),
  touched_at timestamptz not null default now()
);

create index if not exists agent_conversations_user_touched_idx
on public.agent_conversations (user_id, touched_at desc);

comment on table public.agent_conversations is
  'Private ReAgent conversation history synchronized across signed-in devices.';

alter table public.agent_conversations enable row level security;
revoke all on table public.agent_conversations from anon, authenticated;
grant select, insert, update, delete on table public.agent_conversations to service_role;

create or replace function public.touch_agent_conversation()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  new.touched_at := now();
  return new;
end;
$$;

drop trigger if exists touch_agent_conversation_on_update
on public.agent_conversations;
create trigger touch_agent_conversation_on_update
before update on public.agent_conversations
for each row
execute function public.touch_agent_conversation();

create or replace function public.bound_agent_conversation_rows()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  perform pg_advisory_xact_lock(new.user_id);

  if exists (
    select 1
    from public.agent_conversations
    where id = new.id
  ) then
    return new;
  end if;

  if (
    select count(*)
    from public.agent_conversations
    where user_id = new.user_id
  ) >= 50 then
    delete from public.agent_conversations
    where id = (
      select id
      from public.agent_conversations
      where user_id = new.user_id
      order by touched_at asc, created_at asc, id asc
      limit 1
      for update
    );
  end if;

  return new;
end;
$$;

drop trigger if exists bound_agent_conversations_per_user
on public.agent_conversations;
create trigger bound_agent_conversations_per_user
before insert on public.agent_conversations
for each row
execute function public.bound_agent_conversation_rows();

notify pgrst, 'reload schema';

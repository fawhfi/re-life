-- One compact long-term memory and goal plan per ReAgent user.
create table if not exists public.agent_memories (
  user_id bigint primary key references public.app_users(id) on delete cascade,
  summary text not null default ''
    check (char_length(summary) <= 1200),
  goals jsonb not null default '[]'::jsonb
    check (jsonb_typeof(goals) = 'array')
    check (jsonb_array_length(goals) <= 5)
    check (pg_column_size(goals) <= 65536),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.agent_memories is
  'Private, compact ReAgent long-term memory and user goal plans.';

alter table public.agent_memories enable row level security;
revoke all on table public.agent_memories from anon, authenticated;
grant select, insert, update, delete on table public.agent_memories to service_role;

create or replace function public.touch_agent_memory()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists touch_agent_memory_on_update on public.agent_memories;
create trigger touch_agent_memory_on_update
before update on public.agent_memories
for each row
execute function public.touch_agent_memory();

notify pgrst, 'reload schema';

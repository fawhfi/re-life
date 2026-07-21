-- Versioned regional recycling statistics exposed only through the backend.
create table if not exists public.regional_recycling_datasets (
  id bigint generated always as identity primary key,
  dataset_version text not null unique
    check (char_length(dataset_version) between 1 and 64),
  period text not null
    check (char_length(period) between 1 and 100),
  unit text not null
    check (unit = 'tonnes'),
  source text not null
    check (char_length(source) between 1 and 200),
  source_url text not null
    check (char_length(source_url) <= 2048)
    check (source_url ~ '^https://'),
  is_published boolean not null default false,
  published_at timestamptz,
  created_at timestamptz not null default now(),
  check (not is_published or published_at is not null)
);

create index if not exists regional_recycling_datasets_published_idx
on public.regional_recycling_datasets (published_at desc, id desc)
include (dataset_version, period, unit, source, source_url)
where is_published;

create table if not exists public.regional_recycling_data (
  id bigint generated always as identity primary key,
  dataset_id bigint not null
    references public.regional_recycling_datasets(id) on delete cascade,
  region text not null
    check (char_length(region) between 1 and 100),
  recycled_amount numeric(18, 3) not null
    check (recycled_amount >= 0),
  sort_order smallint not null
    check (sort_order between 1 and 100),
  unique (dataset_id, sort_order)
);

create unique index if not exists regional_recycling_data_region_uidx
on public.regional_recycling_data (dataset_id, lower(region));

create index if not exists regional_recycling_data_order_idx
on public.regional_recycling_data (dataset_id, sort_order)
include (region, recycled_amount);

comment on table public.regional_recycling_datasets is
  'Public dataset metadata. Read by the trusted backend; never contains user data.';
comment on table public.regional_recycling_data is
  'Pre-sorted aggregate recycling amounts by region; never contains user data.';

alter table public.regional_recycling_datasets enable row level security;
alter table public.regional_recycling_data enable row level security;

revoke all on table public.regional_recycling_datasets from anon, authenticated;
revoke all on table public.regional_recycling_data from anon, authenticated;
grant select on table public.regional_recycling_datasets to service_role;
grant select on table public.regional_recycling_data to service_role;

notify pgrst, 'reload schema';

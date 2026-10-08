-- SpineSight Supabase schema. Run once in the Supabase SQL editor.
-- Also create a private Storage bucket named "frames".

create table if not exists sweeps (
  id text primary key,
  captured_at timestamptz not null,
  country text not null,
  currency text not null,
  device text default '',
  duration_s numeric default 0,
  packet jsonb,
  created_at timestamptz default now()
);

create table if not exists books (
  sweep_id text references sweeps(id) on delete cascade,
  id text not null,
  shelf text, position int, frame_ref text,
  status text not null check (status in ('identified','unidentified','needs_appraisal')),
  title text, author text, edition text, isbn text,
  spine_height_cm numeric, spine_thickness_cm numeric,
  id_confidence numeric,
  replacement_amount numeric, replacement_source text, replacement_url text,
  used_amount numeric, used_source text, used_url text,
  excluded boolean default false,
  primary key (sweep_id, id)
);

create table if not exists items (
  sweep_id text references sweeps(id) on delete cascade,
  id text not null,
  category text not null, description text, brand_model text, frame_ref text,
  status text not null,
  low numeric, high numeric, source text, url text,
  confidence numeric,
  primary key (sweep_id, id)
);

create table if not exists review_queue (
  sweep_id text references sweeps(id) on delete cascade,
  ref_id text not null,
  reason text not null
);

-- Raw stage outputs, transcripts and agent events. No FK: events are logged before the sweep row exists.
create table if not exists events (
  id bigint generated always as identity primary key,
  sweep_id text not null,
  kind text not null,
  at timestamptz not null,
  payload jsonb not null default '{}'::jsonb
);
create index if not exists events_sweep_idx on events (sweep_id, at);

alter table sweeps enable row level security;
alter table books enable row level security;
alter table items enable row level security;
alter table review_queue enable row level security;
alter table events enable row level security;
-- No policies: only the server (service role) reads and writes.
